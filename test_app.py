import os
os.environ["LEAD_DB"] = "test_leads.db"
os.environ.pop("ANTHROPIC_API_KEY", None)
import pytest
from fastapi.testclient import TestClient
import app as appmod

@pytest.fixture(autouse=True)
def fresh_db():
    if os.path.exists("test_leads.db"):
        os.remove("test_leads.db")
    yield
    if os.path.exists("test_leads.db"):
        os.remove("test_leads.db")

client = TestClient(appmod.app)

def say(lead, text):
    return client.post("/chat", json={"lead_id": lead, "message": text}).json()

def test_full_flow_hot_lead_books_viewing():
    r = say("a", "Hi, interested in a 2-bedroom")
    assert "budget" in r["reply"].lower()
    r = say("a", "around 2m AED")
    assert "area" in r["reply"].lower() or "Which area" in r["reply"]
    r = say("a", "Dubai Marina please")
    assert "When" in r["reply"]
    r = say("a", "within 2 months")
    assert "Available viewing times" in r["reply"] and r["score"] == "hot"
    r = say("a", "2")
    assert r["status"] == "booked" and "confirmed" in r["reply"]
    lead = client.get("/leads").json()[0]
    assert lead["booked_slot"]

def test_handoff():
    r = say("b", "I need a mortgage advice")
    assert r["status"] == "handoff"

def test_followup_only_for_quiet_unbooked_leads():
    say("c", "Hello")
    say("d", "I want to rent")
    out = client.post("/followups/run?hours=0").json()
    assert set(out["followed_up"]) == {"c", "d"}
    msgs = client.get("/leads/c/messages").json()
    assert "Are you still looking" in msgs[-1]["text"]
