"""Lead Responder: instant reply -> qualify -> score -> book viewing -> alert agent.

Runs with an LLM if ANTHROPIC_API_KEY is set, otherwise falls back to simple rules,
so you can test and demo the whole flow without any API key.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

DB_PATH = os.getenv("LEAD_DB", "leads.db")
AGENCY = os.getenv("AGENCY_NAME", "Skyline Properties")
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
USE_LLM = bool(os.getenv("ANTHROPIC_API_KEY") or GEMINI_KEY)
FIELDS = ("budget", "area", "timeline")

app = FastAPI(title="Lead Responder")


@contextmanager
def conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS leads(
        id TEXT PRIMARY KEY, budget TEXT, area TEXT, timeline TEXT,
        score TEXT DEFAULT 'cold', status TEXT DEFAULT 'new',
        offered TEXT DEFAULT '[]', booked_slot TEXT,
        followups INTEGER DEFAULT 0, last_msg_at REAL, first_reply_ms INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT, role TEXT, text TEXT, ts REAL)""")
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ---------- helpers ----------
def next_slots():
    out, day, times = [], dt.date.today(), ["11:00", "15:00", "17:00"]
    while len(out) < 3:
        day += dt.timedelta(days=1)
        if day.weekday() >= 5:  # skip Sat/Sun
            continue
        out.append(f"{day.strftime('%a %d %b')} {times[len(out)]}")
    return out


URGENT = re.compile(r"asap|immediately|now|this month|next month|week|\b[1-3]\s*months?")


def score(lead):
    known = sum(1 for k in FIELDS if lead.get(k))
    if known == 3 and URGENT.search(lead["timeline"].lower()):
        return "hot"
    return "warm" if known >= 2 else "cold"


def notify_agent(text):
    """Stub. Later: send via WhatsApp Business API, Slack or email."""
    line = f"[{dt.datetime.now():%H:%M:%S}] {text}"
    print("AGENT ALERT:", line)
    with open("alerts.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- the two "brains" ----------
SYSTEM = """You are the first-response assistant for {agency}, a real estate agency in Dubai.
Goal: reply warmly and briefly, and find out three things: budget, preferred area, timeline to buy or rent.
Rules:
- Ask for ONE missing detail at a time. Keep replies under 50 words. Reply in the customer's language (English or Arabic).
- Never invent listings, prices, availability, legal or mortgage advice. If asked about those, or the customer wants a human, set handoff true and say an agent will contact them shortly.
- Write Arabic and any non-English text as normal characters, never as \\u escape sequences.
- Greet the customer only in your very first reply. After that, continue naturally without repeating the greeting.
- Do not offer viewing times yourself; the system adds them once all three details are known.
- If the customer is choosing a viewing slot, set chosen_slot to the exact slot text from OFFERED_SLOTS, otherwise null.
Already known: {known}
OFFERED_SLOTS: {offered}
Reply with ONLY JSON: {{"reply": str, "budget": str|null, "area": str|null, "timeline": str|null, "handoff": bool, "chosen_slot": str|null}}"""


def build_system(lead):
    return SYSTEM.format(
        agency=AGENCY,
        known=json.dumps({k: lead[k] for k in FIELDS}),
        offered=lead["offered"],
    )


def parse_json(raw):
    text = re.search(r"\{.*\}", raw, re.S).group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # repair broken \u escapes and stray backslashes the model sometimes emits
        text = re.sub(r"\\u(?![0-9a-fA-F]{4})", "", text)
        text = re.sub(r'\\(?!["\\/bfnrtu])', "", text)
        return json.loads(text)


def anthropic_turn(history, lead):
    from anthropic import Anthropic

    r = Anthropic().messages.create(
        model=MODEL, max_tokens=400, system=build_system(lead),
        messages=[{"role": m["role"], "content": m["text"]} for m in history],
    )
    return parse_json(r.content[0].text)


def gemini_once(history, lead):
    import httpx

    contents = []
    for m in history:  # Gemini uses "model" instead of "assistant"; merge same-role neighbours
        role = "user" if m["role"] == "user" else "model"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + m["text"]
        else:
            contents.append({"role": role, "parts": [{"text": m["text"]}]})
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": GEMINI_KEY},
        json={
            "system_instruction": {"parts": [{"text": build_system(lead)}]},
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 1024,
                "temperature": 0.3,
            },
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    return parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def gemini_turn(history, lead):
    last = None
    for _ in range(2):  # retry once if the model returns unusable JSON
        try:
            return gemini_once(history, lead)
        except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as e:
            last = e
    raise last


def llm_turn(history, lead):
    if os.getenv("ANTHROPIC_API_KEY"):
        return anthropic_turn(history, lead)
    return gemini_turn(history, lead)


AREAS = ["dubai marina", "downtown", "jvc", "business bay", "palm jumeirah",
         "jlt", "dubai hills", "creek harbour", "arjan"]
ASK = {
    "budget": "What budget range are you considering?",
    "area": "Which area do you prefer, for example Dubai Marina or Downtown?",
    "timeline": "When are you planning to move or buy?",
}


def rule_turn(text, lead):
    t = text.lower()
    out = {"budget": None, "area": None, "timeline": None, "handoff": False, "chosen_slot": None}
    m = re.search(r"\d+(?:\.\d+)?\s*(?:million|mil|m|k)\b|\d[\d,]{5,}", t)
    out["budget"] = m.group(0) if m else None
    out["area"] = next((a for a in AREAS if a in t), None)
    m = re.search(r"asap|immediately|this month|next month|\d+\s*(?:weeks?|months?)|this year|next year", t)
    out["timeline"] = m.group(0) if m else None
    out["handoff"] = bool(re.search(r"mortgage|legal|lawyer|human|call me", t))
    offered = json.loads(lead["offered"])
    if offered:
        for k, i in {"1": 0, "first": 0, "2": 1, "second": 1, "3": 2, "third": 2}.items():
            if re.search(rf"\b{k}\b", t):
                out["chosen_slot"] = offered[i]
                break
    known = {k: out[k] or lead[k] for k in FIELDS}
    missing = [k for k in FIELDS if not known[k]]
    greeting = f"Thanks for contacting {AGENCY}! " if lead["status"] == "new" else ""
    out["reply"] = greeting + (ASK[missing[0]] if missing else "Great, I have what I need.")
    return out


# ---------- API ----------
class Msg(BaseModel):
    lead_id: str
    message: str


@app.post("/chat")
def chat(m: Msg):
    start, now = time.perf_counter(), time.time()
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO leads(id,last_msg_at) VALUES(?,?)", (m.lead_id, now))
        c.execute("INSERT INTO messages(lead_id,role,text,ts) VALUES(?,?,?,?)", (m.lead_id, "user", m.message, now))
        lead = dict(c.execute("SELECT * FROM leads WHERE id=?", (m.lead_id,)).fetchone())
        history = [dict(r) for r in c.execute("SELECT role,text FROM messages WHERE lead_id=? ORDER BY id", (m.lead_id,))]

        try:
            data = llm_turn(history, lead) if USE_LLM else rule_turn(m.message, lead)
        except Exception as e:  # never leave a lead without a reply
            print("LLM failed, using rules:", e)
            data = rule_turn(m.message, lead)

        for k in FIELDS:
            if data.get(k):
                lead[k] = str(data[k])
        reply = data.get("reply") or "Thanks! An agent will be in touch shortly."
        offered, status = json.loads(lead["offered"]), lead["status"]

        if data.get("handoff"):
            status = "handoff"
            notify_agent(f"HANDOFF: {m.lead_id} said: {m.message}")
        elif data.get("chosen_slot") in offered and status != "booked":
            lead["booked_slot"], status = data["chosen_slot"], "booked"
            reply = f"Booked! Your viewing is confirmed for {lead['booked_slot']}. Our agent will contact you shortly."
            notify_agent(f"BOOKED: {m.lead_id} viewing {lead['booked_slot']} | {lead['budget']} | {lead['area']} | {lead['timeline']}")
        elif all(lead[k] for k in FIELDS) and status in ("new", "qualifying"):
            offered, status = next_slots(), "offered"
            reply += "\n\nAvailable viewing times:\n" + "\n".join(f"{i+1}) {s}" for i, s in enumerate(offered))
            reply += "\nReply 1, 2 or 3 to book."
            notify_agent(f"QUALIFIED: {m.lead_id} | {lead['budget']} | {lead['area']} | {lead['timeline']}")
        elif status == "offered":
            reply += "\n\nReply 1, 2 or 3 to pick a viewing time."
        elif status == "new":
            status = "qualifying"

        lead["score"] = score(lead)
        ms = int((time.perf_counter() - start) * 1000)
        c.execute(
            """UPDATE leads SET budget=?,area=?,timeline=?,score=?,status=?,offered=?,
               booked_slot=?,last_msg_at=?,first_reply_ms=COALESCE(first_reply_ms,?) WHERE id=?""",
            (lead["budget"], lead["area"], lead["timeline"], lead["score"], status,
             json.dumps(offered), lead["booked_slot"], now, ms, m.lead_id),
        )
        c.execute("INSERT INTO messages(lead_id,role,text,ts) VALUES(?,?,?,?)", (m.lead_id, "assistant", reply, time.time()))
    return {"reply": reply, "reply_ms": ms, "status": status, "score": lead["score"]}


@app.get("/leads")
def leads():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM leads ORDER BY last_msg_at DESC")]


@app.get("/leads/{lead_id}/messages")
def messages(lead_id: str):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT role,text FROM messages WHERE lead_id=? ORDER BY id", (lead_id,))]


@app.post("/followups/run")
def followups(hours: float = 24):
    """Nudge leads that went quiet. Call from a scheduler (cron / Task Scheduler)."""
    cutoff, now, sent = time.time() - hours * 3600, time.time(), []
    with conn() as c:
        rows = c.execute(
            "SELECT id FROM leads WHERE status IN ('qualifying','offered') AND followups<2 AND last_msg_at<=?",
            (cutoff,),
        ).fetchall()
        for r in rows:
            text = f"Hi again from {AGENCY}! Are you still looking for a property? Reply any time and we'll pick up where we left off."
            c.execute("INSERT INTO messages(lead_id,role,text,ts) VALUES(?,?,?,?)", (r["id"], "assistant", text, now))
            c.execute("UPDATE leads SET followups=followups+1,last_msg_at=? WHERE id=?", (now, r["id"]))
            sent.append(r["id"])
    return {"followed_up": sent}


@app.get("/")
def home():
    return FileResponse("static/index.html")
