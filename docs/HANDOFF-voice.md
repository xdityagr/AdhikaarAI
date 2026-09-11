# Handoff — Phase C, inbound voice (Vapi)

Parallelisable with feature work. **Adds one new module and one new router; does
not modify `discovery.py`, `agent.py`, `application.py` or the web app.** The
only files it shares with anyone else are `src/main.py` (one `include_router`
line) and `src/config.py` (a few settings).

A number people can ring, that answers in their language. Inbound only.

---

## Read this before writing any code

### The thing that decides the whole architecture

**Our agent cannot be on a phone call.** This is measured, not assumed:

- `src/agent.py:904` — *"a turn takes twenty to sixty seconds — four model
  round-trips and up to seven lookups"*
- `stream()` emits its text as one block, so time-to-first-word equals
  time-to-full-answer
- **There is no text-to-speech anywhere in this codebase.** `src/speech.py` is
  STT only (Sarvam `saarika:v2.5`, Deepgram `nova-3`)

Sixty seconds of silence on a phone call is a dropped call. So do **not** put
`agent_respond` behind a phone number.

### The architecture that works

**Vapi drives the conversation with its own fast model and calls our engine as
tools over webhooks.** That inverts the latency problem into one already solved —
the lookups are fast, it is the agent loop around them that is slow:

```
discover_with_credit(...)   103–115 ms     (measured, warm, limit=40)
find_schemes tool            110 ms        (the whole tool, end to end)
```

The eight tool implementations in `src/agent.py:694-702` are already callable
without the agent loop. Every one returns `(payload: dict, cards: list, summary: str)`:

| tool | what it answers |
|---|---|
| `find_schemes` | matched against every scheme in the corpus |
| `check_scheme_eligibility` | this scheme's rules against this person |
| `lookup_scheme` | the scheme's published text |
| `search_schemes` | free-text search |
| `price_loan` | the repayment, calculated |
| `find_offices` | offices that can disburse |
| `prepare_application` | fills the form |
| `corpus_stats` | counts |

`summary` is already a spoken-shaped sentence — `find_schemes` returned
*"27 aimed at this person, 423 possible, of 4736"*.

---

## Task 0 — The spike. Do this before committing to Vapi at all.

**Vapi's documentation does not name a single Indic language for either
transcription or text-to-speech.** That is the real risk in this phase; the
plumbing is easy. Half a day, inbound, end to end, Hindi and Tamil:

1. Can Vapi transcribe inbound Hindi and Tamil on a real PSTN call?
2. Can it *speak* Hindi and Tamil, and does it sound like a person or like a
   screen reader?
3. What is the round-trip from end-of-speech to first spoken word with one tool
   call in the middle?

**Report findings before building.** If Indic coverage is not there, the fallback
worth pricing is a Sarvam voice behind Vapi, or Vapi's custom-voice/custom-LLM
route — Sarvam already does STT for 11 Indian languages in this repo and has TTS.
Do not silently build an English-only phone line; a scheme finder that only
answers in English is the problem this product exists to solve.

If the answer is no on all counts, say so and stop. That is a successful spike.

---

## Task 1 — The tool endpoints

`POST /api/voice/tools/{name}` — thin, fast, deterministic, **no model on this
path**. A new `src/voice.py` plus a router, following `src/webhook.py`'s shape.

Requirements:

- Wrap the existing `TOOL_IMPLEMENTATIONS`; do not reimplement matching.
- Return `summary` as the spoken line and `payload` for anything Vapi wants to
  read out in detail. Keep replies short — this is being read aloud, and a list
  of forty schemes is not a sentence.
- **Verify the webhook signature.** `src/meta_whatsapp.py:88` is the pattern to
  copy — `hmac.new(...)` and `hmac.compare_digest`. An unauthenticated endpoint
  that runs our engine for anyone who finds the URL is not acceptable, and these
  routes are being added at a time when nothing else in the API has auth.
- Budget: keep p95 under ~300 ms. The lookups are ~110 ms; the rest is yours.

## Task 2 — Session and language, keyed on the caller's number

**This already exists — do not build a second one.** `user_context` and the
helpers landed with cross-channel memory:

```python
from src.database import load_context, save_context, forget_context
from src.whatsapp_brain import language_if_known, remember_detected_language
```

- Keyed on the phone number, which is the only identifier spanning WhatsApp and
  a call, and the only one somebody hands over by their own action.
- `_EPHEMERAL_CONTEXT_KEYS` (`whatsapp_brain.py:302`) are deliberately not
  persisted — session junk restored days later is worse than no memory.
- A caller who has used WhatsApp should be recognised: same number, same state,
  same caste, same language, without being asked again. That is the point of the
  feature and the easiest thing to get right, because the table is already there.

For a caller with no history, Sarvam's `AUTODETECT` (`speech.py:84`) is how a
first voice note works today; the same approach should decide the call's
language.

STT coverage, for reference (`src/speech.py:63-76`):

- Sarvam: en hi bn mr ta te gu kn ml pa or — **no Assamese, no Urdu**
- Deepgram: en hi bn mr te ta gu kn pa as ur — the reason it stays

## Task 3 — Consent and the recording

Inbound only, so there is no unsolicited-contact problem and cost scales with
real demand. But:

- **Check `has_opted_out` before any outbound anything.** `src/whatsapp_consent.py`.
  `is_loaded()` must be True first — an empty cache means "we have not looked",
  not "nobody opted out", and acting on the second reading would contact every
  person who ever asked us to stop.
- Decide and write down whether calls are recorded, and say so on the call
  before anything is recorded. Do not default this on.
- Never read an Aadhaar number, a bank account number or an OTP aloud, and never
  ask for one. The fraud pattern this audience suffers most is a phone call
  asking for exactly those.

## Task 4 — Verification

The plan asks for **a scripted call transcript in Hindi and Tamil, end to end.**
Not a unit test — a real call, transcribed, pasted into the PR.

Plus:

- a test that every `/api/voice/*` route rejects an unsigned request
- a test that the tool endpoints return the same answer as the corresponding
  `TOOL_IMPLEMENTATIONS` entry, so the voice path cannot drift from the web one
- `pytest` is at **548 passing**; no phase may reduce that

---

## Constraints that are not yours to relax

1. **No model on the eligibility path.** Rates, amounts and verdicts are
   computed, never generated. A model may choose words; it may not decide
   whether someone qualifies. Telling a person they qualify when they do not is
   a real harm and the reason the matcher is deterministic.
2. **Inbound only.** Nobody is called unprompted. The number is published.
3. **Ranking neutrality.** No commercial signal may reach `route_partners`.
   `src/routing.py:162-166` weights sum to 1.00 and `format_cheapest_route`
   independently recomputes and prints the cheapest partner — a paid reorder
   would put a recommendation and a contradiction of it in the same breath.
4. **Nothing about a caller is stored without consent**, and `user_context` is
   the only place it goes.

## Where things are

| | |
|---|---|
| tool implementations | `src/agent.py:694-702` |
| why the agent is too slow | `src/agent.py:904` |
| STT, both providers | `src/speech.py` |
| webhook shape + signature | `src/webhook.py`, `src/meta_whatsapp.py:88` |
| cross-channel memory | `src/database.py:318-340`, `src/whatsapp_brain.py:302-355` |
| consent | `src/whatsapp_consent.py` |
| web ↔ WhatsApp handoff codes | `src/handoff.py` (alphabet omits O/0 and I/1/L for reading aloud — already the right shape for a code spoken down a phone) |
| the plan this comes from | `docs/superpowers/specs/` and the approved Phase C section |
