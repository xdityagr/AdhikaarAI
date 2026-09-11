# Spike — Phase C, inbound voice (Vapi)

**Status: half done. Read the last section before acting on any of it.**

`docs/HANDOFF-voice.md` Task 0 asks three questions and says *report findings
before building*. Two of the three can be answered from published contracts and
from this repo. The third cannot be answered without a Vapi account, a
provisioned number and a person holding a phone — none of which exist here.
What follows separates those carefully, because a documentary answer and a
dialled answer are not the same evidence, and the difference is the whole point
of a spike.

Date: 2026-09-12. Everything below is versioned documentation and live API
responses; re-check before relying on it in a month.

---

## The headline: the premise has moved

The handoff says:

> Vapi's documentation does not name a single Indic language for either
> transcription or text-to-speech.

That is still true **of the page it was read on** — `customization/multilingual`
gives only provider counts ("100+", "125+", "40+") and names no language at all.
It is **no longer true of the per-provider pages**, which now publish explicit
language matrices. The risk this phase was organised around is smaller than it
looked, and it is smaller in a specific, checkable way.

### Q1 — Can Vapi transcribe inbound Hindi and Tamil? **Yes, on paper.**

`transcriber.provider = "deepgram"`, `model = "nova-3"`, `language = "hi"` or
`"ta"`. Both are named in Vapi's own matrix. `language = "multi"` is offered for
code-switching, which matters here — a Tamil question containing an English
scheme name is the normal case, not the edge case.

### Q2 — Can it speak Hindi and Tamil? **Yes, on paper.**

`voice.provider = "11labs"`, `model = "eleven_flash_v2_5"`, `language = "hi"`.
Hindi and Tamil are both named for Flash v2.5 and Multilingual v2, and Vapi notes
that language *enforcement* is supported only on Flash v2.5 — so that is the one
to use, or the model drifts back to English phonology on a mixed sentence.

### Q3 — Round trip, end-of-speech to first spoken word? **Unknown, and unknowable from here.**

Needs an account, a number and a call. It is the one question that decides
whether the design is pleasant or unusable, and it is untouched. See the last
section.

**The spike's kill condition — "if the answer is no on all counts, say so and
stop" — is ruled out.** It is not no on all counts. It is yes, yes, unknown.

---

## The finding that actually changes the plan

The handoff's FAQ section offers two options and ranks them:

> 1. Check whether myScheme's API returns FAQs per language. If it does,
>    backfill them … **This is the right answer — government-published
>    translations, not invented ones.**
> 2. If it does not, translating an FAQ answer at read-time is *acceptable* …

**Neither option describes the real situation.** I called the endpoint.

`GET /schemes/v6/public/schemes/{mongo_id}/faqs?lang=hi` returns HTTP 200 and a
`hi` block containing the full FAQ list. So the answer to "does it return FAQs
per language" is *yes* — and stopping there is the trap.

Measured over **15 randomly drawn schemes × 2 languages = 382 question-and-answer
pairs**:

| | Hindi | Tamil |
|---|---|---|
| **Questions** in the target script | 191/191 — **100%** | 191/191 — **100%** |
| **Answers** in the target script | 0/191 — **0%** | 0/191 — **0%** |

myScheme translates the question and returns the answer in English. Every time.
Hindi, Tamil, Bengali, Malayalam and Assamese all behaved identically on the
three schemes probed in full.

```
lang=hi   Q: स्टैंड-अप इंडिया योजना के तहत ऋण की प्रकृति और आकार क्या है?
          A: Composite loan (inclusive of term loan and working capital)
             between 10 lakh and up to 100 lakh …

lang=ta   Q: ஸ்டாண்ட்-அப் இந்தியா திட்டத்தின் கீழ் கடனின் தன்மை மற்றும் அளவு என்ன?
          A: Composite loan (inclusive of term loan and working capital)
             between 10 lakh and up to 100 lakh …
```

### Why this matters more on a phone than anywhere else

Option 1 as written — backfill the way `scripts/backfill_translations.py`
backfills the rest — would load a per-language `faqs` column that is **half
translated and looks fully translated**. A key-coverage check passes. A row count
passes. A spot check of a *question* passes. And a Hindi caller hears a Hindi
voice read an English sentence, in Hindi phonology, down a phone line, with no
screen to fall back on.

That is worse than the honest English answer we serve today, because it is the
same failure wearing a translation's clothes.

**So the FAQ plan collapses to a third option the handoff did not list:**

- Take the **questions** from myScheme per language. They are free, authoritative,
  government-published, and they are the half that most needs to be in the
  caller's language — they are what a spoken question gets matched against.
- Translate the **answer** at read-time and say on the call that it is a
  translation — the handoff's own option 2, which it already rules *acceptable*
  for quoted content as against an eligibility verdict, which it rules out and
  which nothing here changes.
- Never write a translated answer into the corpus as though it were published.

`src/corpus/myscheme.py:765` currently hardcodes the English block:

```python
faqs = client.sub_resource(scheme_id, "faqs")
items = ((faqs or {}).get("en", {}) or {}).get("faqs") or []
```

`sub_resource` already accepts `lang`. Fetching per-language questions is a
parameter, not a rewrite.

---

## Language coverage is the real constraint, not Hindi and Tamil

Hindi and Tamil were the two *most* likely to be supported everywhere. They
cleared. The phase's actual risk is the tail — and the tail is where this
product's users are.

What the WhatsApp channel serves **today** (`src/speech.py`, Sarvam + Deepgram):

> en · hi · bn · mr · ta · te · gu · kn · ml · pa · or · as · ur — **13**

What each voice route can serve:

| | STT | TTS |
|---|---|---|
| **Vapi native** (Deepgram nova-3 / ElevenLabs Flash v2.5) | en hi bn mr ta te kn ur — **8** | en hi ta — **3** |
| ElevenLabs `eleven_v3` (TTS only) | — | + bn mr te gu kn ml pa ur; **Odia absent** |
| **Sarvam** (custom transcriber / custom voice) | en hi bn mr ta te gu kn ml pa or — **11** | same **11** |

Read together:

- **Vapi's native TTS covers 3 of our 13 languages.** Flash v2.5 — the only model
  with language enforcement — has Hindi, Tamil and English and nothing else of
  ours. That, not transcription, is the binding constraint.
- **Gujarati, Malayalam, Punjabi and Odia are absent from Vapi's Deepgram matrix
  entirely** and are present in Sarvam. **Assamese and Urdu are the reverse.**
  This is the *same complementarity `src/speech.py` already documents* — "Sarvam
  has no Assamese or Urdu; these two are the reason Deepgram stays." The voice
  channel inherits the split unchanged.
- **Assamese has no TTS path at all** among these three. Odia has exactly one
  (Sarvam). Any claim that voice supports the same languages as WhatsApp is
  wrong until that is solved or scoped out in writing.

### The Sarvam fallback is not merely "worth pricing" — it fits exactly

The handoff floats it as a contingency. The contracts line up better than a
contingency usually does:

| Vapi `custom-voice` wants | Sarvam `/text-to-speech` gives |
|---|---|
| sample rate 8000 / 16000 / 22050 / 24000 | 8000 / 16000 / 22050 / 24000 (and higher) |
| raw PCM, mono, 16-bit signed, little-endian | `linear16` codec option |
| `POST` JSON → `application/octet-stream` body | base64 or raw, per codec |
| auth via `server.secret` / `credentialId` | `api-subscription-key` header |

Vapi POSTs:

```json
{ "message": { "type": "voice-request", "text": "…", "sampleRate": 24000,
               "timestamp": 1677123456789, "call": {}, "customer": {} } }
```

…and expects raw PCM back. That is a *small endpoint in `src/voice.py`* — the
same module Task 1 already calls for, under the same signature check Task 1
already requires. It is not a second architecture.

The custom transcriber is heavier: a WebSocket that opens with
`{"type":"start","encoding":"linear16","container":"raw","sampleRate":16000,"channels":2}`,
then binary PCM in and
`{"type":"transcriber-response","transcription":"…","transcriptType":"final"}`
out. Only needed for the languages Vapi's Deepgram cannot reach.

---

## Measured, once the credentials arrived

### Our half of the latency budget is not the problem

Task 1 budgets p95 under ~300 ms. Signed requests through the real router,
warm, 25 runs each:

| tool | p50 | p95 | max |
|---|---|---|---|
| `find_schemes` | 118.6 ms | **138.2 ms** | 140.9 ms |
| `next_question` (the interview) | 120.5 ms | **139.1 ms** | 145.4 ms |
| `corpus_stats` | 35.0 ms | 36.5 ms | 36.8 ms |
| `check_scheme_eligibility` | 9.6 ms | 10.6 ms | 30.4 ms |
| `search_schemes` | 3.8 ms | 4.2 ms | 4.4 ms |

Every one is inside budget with room to spare, and `find_schemes` lands where
the handoff measured it (~110 ms). The adaptive interview costs about the same
as a match, because it *is* one — it runs discovery each turn to see what is
still in play, which is the price of the second question depending on the first.

**This does not answer Q3.** Our endpoint is one link in the chain. ASR
finalisation, the model's turn, TTS first byte and the PSTN leg are still
unmeasured and are most of the round trip. What it does establish is that if the
call feels slow, this is not where to look.

### The provisioned number cannot serve the audience

The account holds one number:

```
+1 571 364 0257   provider: vapi   status: active
```

Vapi's free numbers are **US national use only**. That is a problem specific to
this product rather than a detail:

- The stated reason this channel exists (`docs/PRD-v3.md:290`) is that *"it is
  the only channel that reaches people with no smartphone at all, which in this
  demographic is not a rounding error."*
- Those are exactly the callers for whom an international call is either
  unaffordable or barred outright — ISD is off by default on many Indian prepaid
  plans, so for a large share of the intended audience the number does not fail
  expensively, it simply does not connect.

So `+1 571…` is a **demo path**, fine for proving the technology and for running
the scripted Hindi and Tamil calls Task 4 asks for. It is not the published
helpline. A published number needs an Indian DID imported from a provider
(Twilio, Telnyx, or an Indian CPaaS such as Exotel or Plivo), and Indian inbound
DID carries entity-KYC and telecom-licensing requirements that are worth pricing
before anything is printed on a leaflet.

`scripts/provision_voice.py` warns when it attaches a `+1` number, so this
cannot be forgotten quietly.

## What is still missing, and it is the part that matters

Everything above is documentation and a JSON API. **None of it is a phone call.**
Still unanswered:

1. **Does it sound like a person or a screen reader?** Unanswerable from a support
   matrix. "Tamil is supported" and "a Tamil speaker would not hang up" are
   different claims, and only one of them is written down anywhere.
2. **Latency, end-of-speech to first spoken word, with one tool call in the
   middle.** The handoff budgets p95 < 300 ms for our endpoint and measures the
   lookups at ~110 ms; the rest of the loop — ASR finalisation, the model's turn,
   TTS first byte, the PSTN leg — is unmeasured and is most of it.
3. **Whether Hindi/Tamil enforcement holds** on a sentence containing an English
   scheme name, which is the normal sentence here.
4. **Cost per minute** at these provider combinations, which decides whether the
   number can be published at all.

Credentials have since been added (`VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`,
`VAPI_PHONE_NUMBER_ID`), so what remains is three steps and a phone:

1. **Deploy.** `/api/voice/*` exists in this branch and not on
   `adhikaar-api-vcnc.onrender.com`, which still answers 404. Vapi cannot reach
   a laptop.
2. **Provision.** `python scripts/provision_voice.py --language hi
   --attach-number`, then the same with `--language ta`. Run it with
   `--dry-run` first; it prints the whole assistant with the secret redacted.
3. **Dial `+1 571 364 0257` and talk to it.** In Hindi, then in Tamil. Paste the
   transcripts into the PR, which is what Task 4 actually asks for — not a unit
   test, a real call.

Until (1) and (2) at the top of this section are answered by that call, the
honest status of Phase C's central assumption is **plausible, not
demonstrated.** Everything built so far is built on the plausible half.
