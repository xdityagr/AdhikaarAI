# MVP Plan & Pitch — Adhikaar AI

**Target: a 4-minute pitch that wins the room, plus Q&A.**
Companion to `PRD-v3.md` (features), `data-sources.md` (corpus), `BUSINESS-PLAN.md` (scale story).

> **Build status as of 2026-09-07** — branch `feat/mvp-corpus-routing`, 221 tests passing.
> 11 of 14 items done, plus a web product that was never in this plan. Two things
> in the pitch script below no longer match what exists — both are marked in §1 and
> listed in §2.2. Read those before rehearsing.

---

## 0. The principle

**Build backwards from the pitch.** Write the demo script first, then build only what it needs. Every feature that isn't on screen in those four minutes is Phase 2 — no matter how good it is.

This is not scope-cutting for its own sake. `PRD-v3.md` §12 sets a fallback ladder for a reason: the failure mode for a six-person team with three surfaces is arriving with three things half-done. A tight, rehearsed, fully-working four minutes beats a broad demo that stalls once.

---

## 1. The pitch — 4:00

### 0:00–0:30 · Open with a person, not a statistic

> **Sunita Devi. Ballia district, Uttar Pradesh.** She wants to start a tailoring unit. It will cost ₹1.2 lakh.
>
> There is a government scheme that will lend her 90% of that at **6.5%** — cheaper than any commercial loan in India. She has never heard of it.
>
> And if she had: she wouldn't know which of **five** products fits her, which of **102** channel partners can process it, or whether that partner is even *allowed* to disburse this month.
>
> So she borrows from a moneylender at **5% a month**.

Do not open with the scheme, the ministry, or the tech. Open with her. Everything after this is in service of that sentence.

### 0:30–2:30 · Live demo

| Time | Beat | What the judge sees |
|---|---|---|
| 0:30 | **She types in Hindi** | She types *मुझे सिलाई की दुकान खोलनी है* and the whole app answers in Hindi. Say: *"we never asked her what language she speaks — we detected the script"*. **Voice is NOT built** — do not promise a spoken reply |
| 0:55 | **Six taps, no form** | Purpose, cost, family income, category, who's applying, where. Every question has tappable options; typing is optional. Fast — don't linger |
| 1:10 | **The Why / Why-Not trail** | *Qualifies* for Micro Finance — here's the arithmetic. Does **not** qualify for Term Loan — **and here's why.** Explaining the rejection is the literacy moment |
| 1:20 | **True Cost + Moneylender Comparison** | *"This loan costs her ₹12,568. The same money from a moneylender would cost ₹1,78,200."* **Stop talking for one beat.** This is the emotional peak of the pitch |
| 1:45 | **Map — and an exclusion** | Nearest partners, on a real map. Then show one that is **excluded**, with the reason: *"this agency hasn't utilised its last release — it cannot disburse right now."* Prudential routing, made visible |
| 2:10 | **Cheapest Scheme** | *"She qualifies for three schemes. Micro Finance costs ₹12,568. Udyam Nidhi costs ₹41,957. Same project, same ₹1.08 lakh, ₹29,389 apart — and nobody tells her."* |

> **Every rupee figure above is produced by the code**, not written for the slide. Re-run
> `format_true_cost` / `format_moneylender_comparison` / `format_scheme_comparison`
> before the pitch and copy what comes out. An earlier draft of this script quoted
> ₹22,300, which the calculator does not produce — the script follows the code.

### 2:30–3:15 · The three reveals

This is where you separate from every other team. Deliver them as *"and here's what most people miss."*

> **One.** The problem statement names three schemes. **NSFDC runs five.** The PS's own quoted range — 6.5% to 15% — is arithmetically impossible with three products. We found that by reading the source instead of the brief.
>
> **Two.** Everyone assumes fund-utilisation data is internal to NSFDC. **They publish it.** *[show the spreadsheet]* This is the file dated 31 July. Our router runs on real numbers, not mocks.
>
> **Three.** Her eligibility isn't self-declared — it's **verified against UIDAI's own digital signature**, with no licence required. *[badge flips `DECLARED` → `VERIFIED`]*

### 3:15–4:00 · Scale, the other side, and close

> One engine, **six corporations** — SC, ST, OBC, Safai Karamcharis, minorities, disability.
>
> India's flagship credit portal, **JanSamarth, carries 15 schemes and 269 banks — and zero of these.** Not an oversight: it's built for direct bank lending, and these lend through State Channelizing Agencies. **This is the one large government credit channel with no digital front door.**
>
> And for the agency on the other side: a queue of pre-verified applications, sorted by completeness — instead of a pile of paper. **(Say this as roadmap. The partner console is NOT currently in the UI — see §2.2.)**
>
> Sunita gets the right scheme, at the right price, from a partner who can actually pay her — and she makes **one trip instead of four.**

---

## 2. MVP build sheet

### 2.1 Status against the original 14

Sizes were relative (S ≈ half a day, M ≈ 1–2 days, L ≈ 3+). **11 of 14 done.**

| # | Item | Status | Where it lives |
|---|---|---|---|
| 1 | Plane A corpus — 5 schemes | **Done** | `corpus/v1/schemes.json`, `src/corpus/` |
| 2 | Tier 1 on 5 schemes | **Done** | `src/schemes.py` |
| 3 | Why / Why-Not trail | **Done** | `EligibilityResult.rejections` with stable `rule` tags |
| 4 | Calculator — quarterly + True Cost | **Done** | `src/calculator.py` (`periods_per_year`) |
| 5 | Moneylender Comparison | **Done** | `src/literacy.py` |
| 6 | Utilisation data ingest | **Done, real** | `src/corpus/ingest.py` — 36 states × 9 FYs, to 31 Jul 2026 |
| 7 | Routing + exclusion reasons | **Done** | `src/routing.py` |
| 8 | Map | **Done** | `src/maps.py` — OSM tiles, local cache, offline after one run |
| 9 | Cheapest Scheme + Route | **Done** | Scheme comparison live; partner-rate route stays silent unless a spread is published |
| 10 | Script detection + Hindi | **Exceeded** | 5 languages, not 2 — `src/i18n.py` |
| 11 | Voice in/out | **Not built** | Deferred by decision. Spec still stands: `ai4bharat/indic-conformer-600m-multilingual` for speech-to-text (all 22 languages, MIT) and `ai4bharat/indic-parler-tts` for speech back. Both self-hostable, no vendor |
| 12 | Partner console | **Regressed** | Existed as a tab; the chat rebuild dropped it — see §2.2 |
| 13 | Aadhaar offline XML verify | **Done** | `src/verification.py`, real XMLDSig |
| 14 | Demo ops + cache warming | **Partial** | Tile cache works; no warm-up script yet |

### 2.2 Two gaps that change the pitch

**The partner console is gone from the UI.** It existed as a tab in the first
web portal — a table of every agency with its utilisation and provenance. The
chat-first rebuild replaced that portal and the tab went with it. The engine and
`/api/partners` still work, so it is a UI rebuild, not a data problem. Until it
is back, the 3:30 beat is roadmap, not a demo.

**Voice does not exist.** Script detection on *typed* text is what is built, and
it is genuinely good — type in Devanagari and the whole app switches to Hindi
from the first message. But the original 0:30 beat promised a spoken reply.
Do not promise it.

### 2.3 Built beyond the plan

None of this was in the original 14. It came out of the work and it is now the
larger half of the demo.

| What | Why it matters |
|---|---|
| **Chat-first web product** (`/app`) | The plan assumed WhatsApp plus one console screen. There is now a full conversational web app: splash, language pick, six tappable questions, rich result cards. This is the thing a judge will actually be shown |
| **Landing page** (`/`) | Somewhere to send a judge or a partner that explains the product in ten seconds |
| **Five languages** | Hindi, English, Marathi, Bengali, Tamil — chosen by SC population. Numbers are never translated, only formatted, so a translation bug cannot change what a loan costs |
| **`src/chat.py`** | Same engine as WhatsApp, different presentation: structured cards for a browser instead of the text block WhatsApp is limited to |
| **Provenance-stamped corpus** | Every scheme number carries its source URL and fetch date. This is what makes "we read the source" checkable rather than a claim |
| **Declarative scraper** | `data-sources.md` §7 — a source registry plus extractor strategies, not twenty bespoke scripts |
| **Aadhaar demo mode** | A clearly-labelled demonstration certificate so reveal 3 is showable without UIDAI's real cert, and never presented as UIDAI's |
| **Custom-element library** | `src/web/adhikaar.js` — the cards render from API data, so adding a card type is a server change |

### 2.4 Bugs found and fixed — say these if asked what went wrong

Worth having ready. "What broke?" is a common judge question and a specific
answer beats a shrug.

- **The app could not start.** `AsyncSqliteSaver.from_conn_string()` returns an
  async context manager, not a saver; `.setup()` on it raised. Unit tests stubbed
  the checkpointer, so nothing caught it until the server ran for real.
- **Business loans were offered to education applicants.** Project types lived in
  a module-level dict and a scheme missing from it matched *everything* — which
  happened the moment the corpus grew past three schemes.
- **Quarterly loans were priced monthly**, and every scheme used one global
  84-month tenure instead of its own.
- **A single message contradicted itself**: the intro quoted a 6-month grace and
  `rate_max` while the block underneath said 3 months and used `rate_min`.
- **Men were quoted the women's rebate** — the rate was reduced whenever the
  scheme had a rebate, without checking gender.
- **A Ballia applicant was routed to the Bihar agency.** An SCA channels funds
  within its own state; distance alone cannot make that valid.
- **The prudential rule was inverted.** Low utilisation was *excluding* agencies,
  but an agency below 100% is by definition sitting on undeployed funds. The PS
  names its exclusion criteria as "high NPAs or overdues" — not low utilisation —
  and excluding idle-fund agencies is the opposite of the fund-utilisation goal.

### 2.5 Still explicitly NOT built — say these as roadmap

Voice in and out · telephony IVR · L5 origination, project report (DPR) and
packet assembly · DigiLocker caste/income pull (rung L2) · assisted CSC mode ·
Ground-Truth Loop · the other five corporations (schema ready, unpopulated) ·
full Plane B / Ask Anything.

Every one is specified in `PRD-v3.md`. A judge asking "can you do X" and hearing
*"yes — here is exactly how, it is phase 2"* costs nothing. A half-built X that
breaks on stage costs the round.

**The one worth adding if there is time:** ~10 hardcoded FAQ pairs so an
unexpected question gets an answer instead of a wall. Half a day, disproportionate
insurance.

---

## 3. Team split — six people, six lanes

Mapped to layer boundaries so the interfaces are already defined and people don't collide.

| # | Lane | Owns | Items |
|---|---|---|---|
| 1 | **Corpus & scraper** | `data-sources.md` §7 pipeline, Plane A, utilisation ingest | 1, 6 |
| 2 | **Rules & money** | Tier 1, calculator, literacy templates | 2, 3, 4, 5 |
| 3 | **Channel** | WhatsApp, language detection, voice | 10, 11 |
| 4 | **Routing & maps** | Prudential optimiser, geo, exclusion reasons | 7, 8, 9 |
| 5 | **Console** | Partner web surface | 12 |
| 6 | **Verification & demo ops** | Aadhaar verify, cache warming, rehearsal, pitch | 13, 14 |

Lanes 1 and 2 were the critical path and are done. **Lane 3's voice work was flagged as the biggest technical risk and was deferred rather than started — that call still stands.** Voice only begins once the UI has been reviewed and the partner console is back (§4).

The national rule is 6 members with at least 1 female member. Lane 6 doubles as the pitch owner, and per `rules.md` every member must be able to field a question on any component — rehearse cross-lane, not just your own.

---

## 4. What is left, in order

The original four-week sequence is spent. This is what remains.

**1. Look at the UI.** Two design passes shipped without being seen in a browser
(Chrome on the dev machine cannot reach the local server — TLS interception on
the tunnel, and localhost is unreachable from it). Nothing else matters until
someone opens `/app` on a phone and a laptop and says whether it is good.

**2. Rebuild the partner console** (§2.2). One screen: the agency table with
utilisation and provenance that `/api/partners` already returns. Without it the
3:30 beat has nothing behind it.

**3. Add `GEMINI_API_KEY`.** Free-text understanding currently falls back to
keyword matching. It handles *"I want to open a small tailoring shop"*; it will
not handle a genuinely open question.

**4. Twilio Sandbox** for the live WhatsApp demo — setup is in the README. The
graph is proven end to end; only the transport is untested.

**5. Voice**, if there is time, and only after everything above is solid.

**6. Cache warming + rehearsal.** §5 below. Stop writing code with real buffer
left; that time is worth more spent breaking the demo deliberately.

## 5. Demo ops — the part teams skip and lose on

**Pre-warm every cache on the demo path.** No live LLM call should sit on the critical path. Run the exact demo profile beforehand in every language you will show, so every explanation and every map tile is already cached. A cache-warm demo is deterministic; a cold one is a coin flip on somebody's rate limit.

**Three fallback layers, rehearsed in order:**
1. Live WhatsApp on real infrastructure — the goal
2. Local instance on the laptop, phone on hotspot — if venue wifi fails
3. Screen recording of the full flow — if everything fails. *Record it in week 3, not the night before*

**Deliberately break it in rehearsal.** Income of exactly ₹5,00,000 (the boundary a judge will test). A profile that matches nothing → No Dead Ends must fire. Two messages sent back to back. A half-typed answer, and an answer in the wrong script. An out-of-category user. If any produces a dead end or a silence, that's a bug, not an edge case.

**Own the mock disclosure — don't get caught by it.** Branch-level utilisation and RRB NPA figures are still mocked (`data-sources.md` §5.1). Say it before a judge asks, in the same breath as reveal 2: *"state-level utilisation is real and published; branch-level isn't published by anyone, so that's representative data, and here's the rule it feeds."* Volunteered, it's rigour. Extracted under questioning, it's a gap.

---

## 6. Q&A prep — the four questions that will come

**"How much of this is real versus mocked?"**
Lead with the split. Scheme data, eligibility rules, partner directory, state-level utilisation: real and sourced. Branch-level utilisation and RRB NPA series: mocked, because no public source publishes them — and that's a finding, not a gap. The *rules* are real in every case.

**"Isn't the government already building this?"**
PM SURAJ exists and we integrate with it rather than compete. JanSamarth exists and covers 15 schemes — none of these. Our defensible position is being the operator they adopt, not the portal they replace.

**"You're charging poor people to access welfare?"**
No. Eligibility, EMI, literacy, the locator and the checklist are free permanently. Only optional assisted filing is ever paid, the free path is shown with equal prominence, and the beneficiary is the **last** payer in the waterfall behind CSR, partner and B2G. Target: beneficiary-paid share trends to zero.

**"Why should we believe your numbers when your own docs say sources disagree?"**
Because we resolved it and can show our work. The rate conflict was a wrong-model problem — three schemes versus five. The income conflict was stale data: ₹5 lakh, rural and urban, effective 7 January 2026. Every field in our corpus carries a source URL and a fetch date. **That the information is this fragmented is the problem statement's own thesis — and it's why a maintained corpus is the product.**

---

**"Is that Aadhaar check real?"**
The cryptography is real: full enveloped XMLDSig verification — the document is
canonicalised, digested and compared, then the signature is RSA-verified over the
signed info. Tampering with the name or the address is caught, and the tests prove
it. What is not real in the demo is the *certificate*: UIDAI distributes its own
and we do not bundle it, so the demo verifies against a clearly-labelled
demonstration certificate and says so on screen. On a real file it is the same
check. Also worth saying: this needs no licence — offline e-KYC makes us an
Offline Verification Seeking Entity, not an AUA, and the file contains no Aadhaar
number at all.

**"Why should we trust the interface if you built it fast?"**
Everything a borrower sees that involves money is a deterministic template, not
model output — `src/literacy.py`. No rupee figure on screen can be hallucinated.
The model writes the greeting, nothing else.

---

## 7. The one-sentence version

> Every other platform tells you which scheme you *might* qualify for. Adhikaar AI proves you qualify, tells you what the loan actually costs against the moneylender you'd otherwise use, and routes you to a partner that can actually disburse this month — in your own language, in your own script.

*(The earlier version of this line ended "by voice if you can't read". Voice is not built. Do not say it.)*
