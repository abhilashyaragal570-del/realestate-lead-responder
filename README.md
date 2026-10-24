# Lead Responder (demo v1)

Instant reply -> qualify (budget, area, timeline) -> score hot/warm/cold -> offer viewing slots -> book -> alert agent -> follow up quiet leads.

## Run (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# optional: use the real LLM (otherwise rule-based mode runs)
$env:ANTHROPIC_API_KEY="your-key"
uvicorn app:app --reload
```
Open http://127.0.0.1:8000 and chat as a customer. Run tests with `pytest`.

## Demo script (for your 2-minute video)
1. "Hi, interested in a 2-bedroom"
2. "around 2m AED" -> "Dubai Marina" -> "within 2 months"
3. Bot offers 3 slots -> reply "2" -> booked; dashboard shows HOT; check alerts.log
4. Start a new lead, send one message, click "Run follow-up"

## Next steps
- Replace notify_agent() with WhatsApp / Slack
- Replace next_slots() + booking with Google Calendar
- Connect real WhatsApp Business API webhook (Meta Cloud API) to POST /chat
- Replace SQLite with Postgres when you have real clients
