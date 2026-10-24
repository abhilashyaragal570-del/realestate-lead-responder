# Lead Responder: instant replies for real estate agencies

Replies to every new enquiry in seconds, finds out the budget, area and timeline, books the viewing and alerts your agent. Works in English and Arabic.

**Demo video:** [Watch the demo](https://youtu.be/jI2hQHyUkek)

*Skyline Properties in the demo is a fictional agency.*

## The problem

- Enquiries arrive at night, on weekends and while agents are out on viewings.
- A slow reply gives the buyer time to talk to another agency.
- Agents lose time asking the same three questions every day: budget, area and timeline.

## What it does

- **Instant reply** to every new message, 24/7.
- **Qualifies the lead** by asking one question at a time: budget, area, timeline.
- **Scores the lead** as hot, warm or cold.
- **Offers three viewing times** and books the one the customer picks.
- **Alerts the agent** when a lead is qualified, a viewing is booked, or a human is needed.
- **Hands off to a human** for mortgage, legal, price or availability questions, or when the customer asks for a person.
- **English and Arabic**, replying in the customer's language.
- **Agent dashboard** showing every lead, its score, average first-reply time and booked viewings.

## How it works

```
Customer message
      |
      v
POST /chat  (FastAPI)
      |
      +--> AI model reads the conversation and replies in plain text
      |    (rule-based fallback if no API key is set)
      |
      +--> Parse reply: budget, area, timeline, handoff flag, chosen slot
      |
      +--> Update the lead in SQLite, score it, then one of:
             - handoff  -> alert the agent
             - slot picked -> book it, confirm, alert the agent
             - all details known -> offer 3 viewing times
      |
      v
Reply to customer + live agent dashboard
```

Choosing a viewing slot is checked in code, not left to the model, so a booking never depends on the model's wording.

## Tech stack

- Python, FastAPI, Uvicorn
- SQLite for leads and messages
- Gemini API (or Anthropic API if `ANTHROPIC_API_KEY` is set), called over HTTP with `httpx`
- Plain HTML and JavaScript dashboard in `static/index.html`
- pytest (3 tests, run offline)

## Run it locally (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GEMINI_API_KEY = "your-key-here"
python -m uvicorn app:app --reload
```

Open http://127.0.0.1:8000 and chat as a customer.

Without an API key the app runs in a simple rule-based mode, which is useful for testing.

Optional settings: `GEMINI_MODEL`, `AGENCY_NAME`, `LEAD_DB`.

## Tests

```powershell
pytest -q
```

The tests do not call any AI service, so they give the same result on any machine.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | Send a customer message, get the reply and lead status |
| GET | `/leads` | List all leads |
| GET | `/leads/{lead_id}/messages` | Full conversation for one lead |
| POST | `/followups/run` | Follow up leads that went quiet |
| GET | `/` | Customer chat and agent dashboard |

## What this demo is, and is not

- It runs in a web chat. It is not connected to WhatsApp yet.
- Viewing times are sample slots, not a real calendar.
- Agent alerts are written to `alerts.log`, not sent to WhatsApp or Slack yet.
- Data is stored in a local SQLite file. Your API key stays in an environment variable and is never committed.

## Roadmap

- WhatsApp Business API (Meta Cloud API) webhook into `/chat`
- Google Calendar for real viewing slots and booking
- Agent alerts on WhatsApp or Slack
- Postgres for real client data

## Work with me

I build lead-response automation for real estate agencies. I can run a **free one-week pilot** on one of your lead sources.

- Name: Abhilash
- Contact: abhilashyaragal570@gmail.com