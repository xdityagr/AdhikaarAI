# Yojna Setu — SIH26092

**AI-Driven Scheme Matching for NSFDC Credit Schemes**  
Smart India Hackathon 2026 · PS26092 · Ministry of Social Justice & Empowerment

WhatsApp-first assistant that helps SC beneficiaries find NSFDC loan/education schemes they qualify for, estimates their EMI, and locates the nearest eligible Channel Partner.

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/xdityagr/AdhikaarAI.git
cd YojnaSetu

# 2. Create venv and install
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -e ".[dev]"

# 3. Configure
cp .env.example .env
# Edit .env with your Twilio credentials

# 4. Run
uvicorn src.main:app --reload --port 8000

# 5. Test
pytest
```

## Run the web portal locally

```bash
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000
# open http://localhost:8000
```

Three tabs:
- **Find a scheme** — the beneficiary flow: eligibility, why you don't qualify for
  the rest, what the loan really costs against a moneylender, and which partner
  can actually disburse.
- **Channel partners** — every agency with the figure each prudential rule is
  assessed against, and whether that figure is published or representative.
- **Scheme corpus** — all five NSFDC schemes with their provenance.

No API keys needed for the portal — the whole path is deterministic, with no LLM
call. WhatsApp needs Twilio credentials in `.env`; the portal does not.

## Connect WhatsApp (Twilio Sandbox)

The Sandbox is free and needs no WhatsApp Business Account. A trial account
includes **$15 credit and 100 free WhatsApp messages**, and expires after 30
days — plenty for a demo, but create it close to the event, not months before.

**1. Twilio account** — sign up, then Console → Messaging → Try it out →
*Send a WhatsApp message*. You get a shared sandbox number (`+14155238886`) and
a join code.

**2. Every tester opts in.** Each phone that will talk to the bot sends
`join <your-code>` to `+14155238886` on WhatsApp. Without this the sandbox will
not deliver to that number — so do it for every phone that touches the demo,
including the one you hand a judge.

**3. Expose the local server.** Twilio must reach your webhook over HTTPS:

```bash
cloudflared tunnel --url http://localhost:8000     # or: ngrok http 8000
```

**4. Point the sandbox at it.** In the sandbox settings, set
*When a message comes in* to `https://<your-tunnel>/webhook/whatsapp`, method
**POST**.

**5. Configure `.env`:**

```
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
WEBHOOK_BASE_URL=https://<your-tunnel>       # must match exactly, or signature checks fail
WEBHOOK_VERIFY_SIGNATURES=true
```

`WEBHOOK_BASE_URL` is used to reconstruct the signed URL. If it doesn't match
what Twilio called, every request 403s — that is the single most common setup
failure here.

**6. Restart and message the sandbox** from an opted-in phone. Send anything,
then `START`, then answer the five questions.

### Sandbox limits worth knowing before demo day

- The number is **shared** — the join code is what routes messages to you.
- Opt-in **expires after 72 hours of inactivity**; re-send the join code on the day.
- Outside a 24-hour window from the user's last message you can only send
  pre-approved templates. Our flow is always reactive, so this doesn't bite.
- Trial accounts prepend a "Sent from your Twilio trial account" line.

## Architecture

Three-tier recommendation pipeline:
1. **Tier 1 — Deterministic rules engine** (income, project cost, category thresholds)
2. **Tier 2 — Light semantic extraction** (free text → structured fields via Gemini)
3. **Tier 3 — Prudential/geo routing** (partner eligibility + Haversine distance)

See `docs/architecture.md` for the full spec.

## Project Structure

```
src/
├── main.py        # FastAPI app, lifecycle management
├── config.py      # All settings + scheme parameters from rules.md
├── database.py    # Async SQLite (WAL mode)
├── webhook.py     # Twilio webhook — verify, idempotency, enqueue, 200
├── worker.py      # Async message queue + LangGraph processing
├── graph.py       # LangGraph conversation state machine
└── whatsapp.py    # Outbound message sender (Twilio)
```

## Current Phase

**Phase 0** — Webhook → queue → worker skeleton with idempotency + LangGraph state persistence.

## License

MIT