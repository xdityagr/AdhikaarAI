# PRD v3 — Adhikaar AI

**SIH 2026 · PS26092 · AI-Driven Scheme Matching for Marginalized Entrepreneurs**
Ministry of Social Justice & Empowerment · Category: Software · Theme: Smart Automation

> **v3 supersedes `PRD.pdf` (v2).** v2 was a well-built *hackathon deliverable checklist*. v3 is a product with a wedge. The reliability core, the deterministic-eligibility discipline and the honest-about-mocks ethos of v2 are kept intact and inherited wholesale — those were right. What changes is scope, data, and what the thing is *for*.
>
> Companion docs: `MVP-PLAN.md` (what to build first + the 4-minute pitch) · `BUSINESS-PLAN.md` (market, model, moats, GTM) · `data-sources.md` (every source, fetch date, confidence) · `architecture.md` (technical spec — needs updating against §5) · `rules.md` (**superseded on scheme numbers and eligibility** — see `data-sources.md` §3 and §4).

---

## 0. Snapshot

**Adhikaar AI is the origination layer for India's social-justice credit channel.**

Not a chatbot. The rail between a beneficiary and a channel partner who can actually disburse — covering discovery, *proof* of eligibility, financial literacy, correct routing, and a complete application packet that doesn't bounce.

One sentence for a judge:

> Every other platform tells you which scheme you *might* qualify for. Adhikaar AI proves you qualify, teaches you what the loan actually costs, writes your project report, and routes you to a partner that can disburse this month — or, when the rules require you to show up in person, makes sure your one trip works.

---

## 1. What the problem statement actually says

The PS is more specific than it first reads. Three things in its own text are load-bearing and easy to skim past.

### 1.1 The PS describes five schemes, not three

The PS names three products but quotes ranges that three products cannot produce:

> "interest rates (e.g., **6.5% to 15% depending on the scheme**)" and "moratorium periods (**3 to 12 months**)"

With Micro Finance / Term Loan / Educational Loan alone, you cannot reach 15%, and you cannot reach a 12-month moratorium. With NSFDC's actual product line you reach both exactly:

| Scheme | Project ceiling | Beneficiary rate | Tenure | Moratorium |
|---|---|---|---|---|
| Micro Finance (MFS) | ≤ ₹1.40 L | **6.5%** | 3 yr | 3 mo |
| Term Loan | ₹1.40 L – ₹50 L | **8%** | 7 yr | 6 mo (**12 mo** plantation/construction) |
| Aajeevika Micro-Finance | ≤ ₹1.40 L | **15%** | 3 yr | 3 mo |
| Udyam Nidhi (UNY) | ≤ ₹5 L | **13–15%** | 5 yr | 3 mo |
| Educational Loan (ELS) | ≤ ₹40 L / 90% of fee | **6.5%** | up to 12 yr | course + 1 yr |

*Source: `nsfdc.nic.in/scheme`, fetched 2026-09-03. Full corpus — dual rates, repayment frequency, partner-type rate variation — in `data-sources.md` §3.*

Three details this table flattens, each of which matters downstream: repayment is **quarterly**, not monthly (§5.3); every scheme publishes **two** rates, one to the channel partner and one to the beneficiary, and the spread is the partner's margin; and Udyam Nidhi's beneficiary rate **depends on which partner type processes it** (§5.4).

The PS's stated range is the **span across the portfolio**, and the phrase "depending on the scheme" says so outright. `rules.md` spent five research passes treating this as irreconcilable source conflict and concluded it "hasn't converged and won't." It had converged; the model had the wrong number of schemes in it.

**This is a Problem Understanding asset, not an erratum.** Say it out loud: *"The PS names three products. NSFDC runs five, and the rate and moratorium ranges quoted in the PS are only explicable once you know all five. A three-scheme build cannot reproduce the PS's own numbers."*

### 1.2 Deliverable 3 is a **Router**, not just a Locator

The PS names the third deliverable "Geo-Spatial Partner Locator **& Router**," names the failure mode as "**misrouted applications**," and asks that applications "aren't sent to partners with high NPAs or overdues." All three presuppose applications *flowing through the system*. Reading deliverable 3 as a locator silently drops half of it.

### 1.3 Impact goals are graded, and one of them has no obvious feature

> "Enhance **financial literacy** among the target demographic regarding concessional lending."
> "Improve **transparency and efficiency**... ensuring **faster disbursements** and **better fund utilization**."

A recommender plus an EMI number is not financial literacy. These are 20% of the rubric and need actual features — §7.2, §7.3, §7.4.

### 1.4 One hard constraint

> "**direct loan applications are not entertained**"

Applications go to a **channel partner**, who makes the credit decision. Adhikaar AI never submits to NSFDC. PM SURAJ (`pmsuraj.dosje.gov.in`) is where a beneficiary registers, not somewhere we file on their behalf. Everything in §9 respects this.

---

## 2. What was wrong with v2

Stated plainly, because the fixes are the substance of v3.

| v2 | Reality |
|---|---|
| Modelled 3 schemes | NSFDC runs 5; the PS's own numbers prove it (§1.1) |
| "Nobody outside NSFDC has utilisation data in real time, and no other team will either" → mocked Tier 3 | NSFDC **publishes** state-wise cumulative funds utilisation as Excel, current to 2026-07-31 |
| Eligibility = self-declared, unverified | Caste and income are the two facts that gate everything, and both are verifiable |
| Recommend, then stop | The PS's own words point at routing and application flow |
| No financial-literacy feature | It's an explicit impact goal |
| Router as a compliance filter | "Better fund utilisation" needs an **optimiser** |
| Haversine only | The PS says "*Integration of a mapping service*" |
| No `education_status` field | The PS names it as a required intake input |
| Scheme = 11 numeric fields | The official pages also carry purpose, a 148-item activity taxonomy, document lists, application routes, FAQs and forms. A numbers-only corpus can't answer a beneficiary's actual questions (§5.1) |
| Individuals only | Partnership firms and cooperative societies are eligible too |
| Monthly EMI | NSFDC repayment is **quarterly** |
| One rate per scheme | Udyam Nidhi's beneficiary rate depends on **which partner type** processes it (§5.4) |
| Scalability = "NBCFDC is similar" (one line) | Six corporations, a real market, a real model |

---

## 3. Users

**Primary — the beneficiary.** SC, family income ≤ ₹5 L, low-end Android, WhatsApp-literate but often not text-literate, more comfortable in a regional language. Frequently a daily-wage earner for whom **each branch visit costs a day's wages plus bus fare** — this single fact drives more design decisions in this document than any other.

**Primary — the assisted operator.** A CSC/VLE operator, SCA field staff member, SHG coordinator or NGO worker completing the flow *on behalf of* a beneficiary. This is the real Indian last mile, and it is the only part of this design that attacks the *awareness* problem, because these people already have outreach to exactly this demographic. Not a secondary surface — see §6.3.

**Primary — the channel partner.** SCA / PSB / RRB / NBFC-MFI staff, currently drowning in incomplete and misrouted paper. This is the "transparency and efficiency" half of the PS's impact goals, and the demand side of the business.

**Secondary — NSFDC / MoSJE.** Wants deployment, utilisation, and coverage visibility. Consumer of §7.4's aggregate views. The buyer in `BUSINESS-PLAN.md`.

---

## 4. PS compliance matrix

Every explicit requirement, mapped. This table is the answer to "did you actually solve the problem statement."

| PS requirement (verbatim) | Where | Beyond baseline |
|---|---|---|
| "AI/rule-based engine... project type, estimated cost, income level, **education status**" | L2 §5.2 | `education_status` also drives delivery-mode adaptation + Train-then-Credit (§7.1) |
| "recommends the most suitable credit **or educational** loan scheme" | L2/L3 | 5-scheme corpus, side-by-side comparison, Why/Why-Not trail |
| "dynamic tool to calculate projected EMIs" | L3 §5.3 | 3 moratorium treatments; True Cost, not just EMI |
| "maximum loan limits, interest rates (6.5%–15%), moratorium (3–12 months)" | L3 + corpus | All five rate bands reproduce the PS range exactly |
| "**Integration of a mapping service**" | L4 §5.4 | Leaflet/OSM + OSRM road distance + native WhatsApp location + Coverage-Gap Map |
| "identify the nearest eligible Channel Partner (SCA/Bank/NBFC-MFI)" | L4 | Corpus carries **8** partner categories, not the 4 the PS lists |
| "based on the user's location **and** the partner's current fund utilization eligibility" | L4 | **Real published utilisation data**, not mocked |
| "ensuring applications aren't sent to partners with high NPAs or overdues" | L4 | Hard exclusion on prudential norms; everything else scored |
| "intelligent, **multi-lingual** digital platform" | §6.5 | Language buttons + IndicTrans2 + voice for non-literate users |
| "over 100 Channel Partners" | L1 §5.1 | Ingested from the official directory (8 categories) |
| "direct loan applications are not entertained" | §9 | Packet routes to a **channel partner**, never to NSFDC |
| **Impact: enhance financial literacy** | §7.2 | Eight features, seven of them deterministic |
| **Impact: transparency + efficiency** | §7.3, §6.2 | Partner console, SLA clock, Ground-Truth Loop |
| **Impact: faster disbursements** | §7.3 | Zero-Rework Packet, One-Trip Promise, Speed Flywheel |
| **Impact: better fund utilization** | §7.4 | Filter→optimiser, idle-fund matching, NPA reduction by design |
| Theme: **Smart Automation** | throughout | The automated artifact is the *packet*, not the chat |

---

## 5. Architecture — five layers

Each layer has one job, a defined interface, and is independently testable. v2's non-negotiables (async webhook, idempotency, LangGraph checkpointer, deterministic eligibility) are **inherited unchanged** and are not re-litigated here — see `architecture.md`.

```
                 WhatsApp        Web/Assisted        Partner Console      Voice/IVR
                     |                |                     |                 |
                     +--------+-------+----------+----------+--------+--------+
                              |                  |                   |
                        L5  ORIGINATION   (packet, DPR, routing, tracking)
                              |
                        L4  ROUTING       (map, prudential optimiser, load balance)
                              |
                        L3  ADVISORY      (EMI, True Cost, literacy, comparison)
                              |
                        L2  ELIGIBILITY   (deterministic rules + proof grading)
                              |
                        L1  CORPUS        (ingest, version, provenance-stamp)
```

### 5.1 L1 — Corpus

Ingests and versions everything the rest of the system reasons over. **Every fact carries `source_url` + `fetched_at` + `confidence`.** No number enters the system unattributed — this is `rules.md`'s config-over-hardcode discipline generalised from a config file to a pipeline.

Full schema, sources and confidence tags: `data-sources.md`.

**The corpus is a knowledge base, not a parameter table.** A scheme is not eleven numbers — the official pages carry purpose, eligibility narrative, an official 148-item activity taxonomy, application routes, document lists, FAQ pairs, downloadable forms and a helpline. An assistant that only knows the numbers is a calculator with a chat interface, while a beneficiary's real questions are *"what papers do I need," "do I need collateral," "can my wife and I apply together," "who do I call."*

So the schema splits by **how a field may be used** — which is the safety property that matters:

| Plane | Content | Consumed by | Rule |
|---|---|---|---|
| **A — Structured** | typed numbers, enums, booleans | Tier 1 eligibility, calculator, router | **Deterministic. Never LLM-touched** |
| **B — Narrative** | purpose, benefits, eligibility prose, process, documents, FAQs | Retrieval → LLM Q&A | **LLM may quote it; never decide from it** |
| **C — Assets** | forms, guidelines, circulars | Served as links | Cached, checksummed |

**The wall between A and B is the whole discipline.** The model may answer *"what documents do I need?"* from Plane B. *"Am I eligible?"* is only ever Plane A. This preserves v2's "eligibility is never the model's job" rule while making the assistant genuinely conversational — and it means a Plane B hallucination can never produce a wrong eligibility verdict.

Plane B mirrors **myScheme's national section taxonomy** (Details · Benefits · Eligibility · Application Process · Documents Required · FAQs · Sources), MeitY's de facto standard across 4,700+ schemes. Mirroring it buys interoperability now and lets us ingest myScheme wholesale in Phase 4 without a migration.

Populated from: the 5 NSFDC scheme records (other five corporations schema-ready, populated later) · the 148-activity taxonomy · NSFDC's 8 official partner-category PDFs (**102 partners**) · the published performance/utilisation Excel files, monthly · `channel_capability` per (scheme × partner type × state), §9.1 · ground-truth corrections from L5, §7.3.

**Corpus versioning is a correctness requirement, not hygiene.** Every recommendation records which corpus version produced it, so any past recommendation is reproducible and auditable. And these numbers demonstrably *do* change — NSFDC's income ceiling has an effective date of 2026-01-07 (`data-sources.md` §4.2). A recommendation given in September must still be explainable in March.

**Plane A changes gate; Plane B changes flow.** A changed interest rate blocks promotion until a human reviews it. A reworded FAQ promotes automatically. Different blast radius, different ceremony.

### 5.2 L2 — Eligibility

**Deterministic. Never the model's job.** v2 was right and this does not change: an LLM must never decide whether someone qualifies. Boundary cases (income at exactly ₹5,00,000) must be correct 100% of the time, and a judge will test exactly that.

What's new:

**Proof grading.** Every input fact carries a grade, and it propagates to the output:

| Grade | Source | Meaning |
|---|---|---|
| `VERIFIED` | UIDAI-signed XML, DigiLocker certificate | cryptographically or legally established |
| `DECLARED` | user-stated | good faith, unverified |
| `INFERRED` | derived from other fields | shown as such |

A result reading *"Eligible — income VERIFIED, category VERIFIED"* is a different object from *"Likely eligible — all facts declared."* The first is something a partner can act on. **That distinction is the product.** See §8.

**`education_status` — earning its place three times** (PS-mandated field, §4):
1. **Scheme fork** — credit vs. ELS, plus the ELS sub-flow (course, institution, India/abroad, admission confirmed, fee, duration)
2. **Delivery adaptation** — low formal education auto-switches to voice-first, shorter sentences, more buttons. Accessibility derived from a required field
3. **Train-then-Credit** (§7.1)

**Family income, not personal income.** The PS says *annual family income*. v2's field is `annual_income`. In a multi-earner household people routinely answer the wrong one, which silently breaks the ₹5 L threshold that gates everything. Needs an explicit earner-sum helper, not a relabelled field.

**Applicant types — v2 modelled only individuals.** NSFDC also lends to **partnership firms and cooperative societies**, provided *every* member is SC and each member's family income is under the ceiling. That's a different eligibility shape (all-members-must-qualify), not a checkbox, and SHG-adjacent group lending is common in exactly this demographic.

**Free-text classification maps to NSFDC's own 148 activities, not to categories we invented.** `/indicative-activities` publishes an official taxonomy — 20 agricultural & allied, 51 small industry, 77 service & transport. Classifying *"I want to open a small tailoring shop"* against that list is more accurate than an LLM inventing buckets, and it's officially defensible: *"we classify against NSFDC's published indicative activities."* The list's own closing clause — *"any other legal and viable income-generating business activity may be considered"* — means an unmatched activity is never a dead end; it becomes "may be considered, here's who to ask." This is the Tier 2 upgrade, and it *shrinks* the model's job, which is the right direction.

**No Dead Ends.** A user who turns out not to be SC is handed to the right corporation — OBC→NBCFDC, ST→NSTFDC, safai karamchari→NSKFDC, minority→NMDFC, disability→NHFDC — not told "sorry." This is the six-corporation architecture made concrete at the eligibility layer, and it is what stops the demo dead-ending when a judge tests an out-of-scope profile.

### 5.3 L3 — Advisory

Instalments across all five rate bands; three moratorium treatments (simple-interest, capitalised, subvention) inherited from v2; scheme-vs-scheme comparison; cached explanation generation. The financial-literacy features in §7.2 live here.

**Repayment is quarterly, not monthly.** NSFDC's published terms are quarterly instalments for Micro Finance, Term Loan and Aajeevika; quarterly or half-yearly for Udyam Nidhi. The PS asks for "EMIs" and v2's calculator computes a monthly figure — so **show both**: the real quarterly instalment (what they will actually be asked to pay) and a monthly equivalent (what they should budget). This is a small correctness fix that makes every number in the demo true rather than subtly wrong, and anyone from the sector will notice it.

**Ask Anything.** With Plane B in the corpus, the assistant answers open questions — *do I need collateral, can my wife and I apply together, what if I don't have a shop yet, what happens if I miss a payment* — retrieved and cited from official text, never invented. Three guardrails: every answer names its scheme and section; an FAQ match returns the official answer **verbatim** rather than paraphrasing it; and any question that resolves to an eligibility decision is routed to Plane A, never answered from prose. No retrieved block means *"I don't have that — here's the helpline,"* never a guess.

### 5.4 L4 — Routing

**Mapping (the PS asks for it literally).**
- **Leaflet + OpenStreetMap** in console and assisted mode — free, no API key
- **Static map image** pushed to WhatsApp with pins, plus a **native WhatsApp location message** for the chosen branch → one tap opens the user's own maps app for directions
- **OSRM road distance**, not only Haversine. Crow-flies distance lies badly in hilly and rural terrain, and "nearest" is the entire point of the deliverable

**Filter → optimiser.** Hard exclusions stay hard — a partner that legally cannot disburse is *excluded*, never merely down-weighted:

```python
# HARD EXCLUSIONS (prudential norms — real rules, see data-sources.md §3)
#   SCA: cumulative_utilisation >= 1.0 AND NOT has_active_overdues
#   RRB: net NPA < 15% in >=3 of preceding 6 FYs AND net profit in >=3 of 6
#   Any: scheme not in partner's processing mandate

score = w1 * prudential_headroom        # how comfortably cleared, not just pass/fail
      + w2 * deployable_headroom        # released-but-undisbursed funds in hand
      + w3 * scheme_capability_match    # an MFI-only partner cannot process Rs 45L
      + w4 * travel_accessibility       # road distance + realistic travel cost
      + w5 * historical_time_to_disburse
      + w6 * borrower_cost              # THE RATE DEPENDS ON THE PARTNER -- see below
```

**The router is also a price optimiser.** Udyam Nidhi is **13% via a Cooperative Bank or Society and 15% via a Small Finance Bank** — same scheme, same borrower, different price, decided purely by which partner processes it. Nobody tells beneficiaries this. So:

> *"The Small Finance Bank is 4 km away at 15%. The Cooperative Bank is 11 km away at 13%. Over your ₹4.5 L loan, those extra 7 km save you ₹—."*

Distance versus lifetime cost, made explicit and personal. That is "financial literacy regarding concessional lending" in the PS's own words, and it is not a comparison any competing team will be positioned to make.

Two distinct signals that v2 collapsed into one, and getting them apart is what makes the optimiser work:

- **Fresh-release eligibility** — utilisation ≥ 100% + zero overdues. Governs whether NSFDC releases *new* money to that SCA.
- **Deployable capacity now** — funds already released but not yet disbursed.

A partner sitting on idle funds is one the system should route applicants *toward*. That is literally what "better fund utilisation" means, and it is the opposite of what a naive high-utilisation-is-good filter does.

**Capacity-aware load balancing.** Routing every applicant to the single best partner builds a queue and recreates the delay we're solving. Distribute across viable partners in proportion to headroom.

### 5.5 L5 — Origination

Document checklist → verification pull → AI project report → packet assembly → route to channel partner → track. Full treatment in §9.

---

## 6. Surfaces

### 6.1 WhatsApp — beneficiary
Zero install, already built and reliable (v2's Phase 0–3). Structured input (buttons/lists/Flows) primary, free text as fallback. Language selection by button.

### 6.2 Web console — channel partner / SCA
The demand side, and the piece no competing team will build.

- Inbound queue of **pre-verified, correctly-routed** applications
- Triage by completeness and age, **not arrival order** — complete packets clear fast
- One-tap "request missing document" → messages the beneficiary on WhatsApp directly, closing a loop that today costs a phone call or a wasted branch visit
- Own prudential standing, deployable headroom, ageing SLA clock
- Coverage-Gap Map (§7.4)

### 6.3 Assisted mode — CSC / VLE / field staff
**Load-bearing, not a nice-to-have.** The PS's root cause is *awareness* — but a WhatsApp bot only reaches people who already know it exists, which is the same discovery problem one layer up. Assisted mode is the only part of this design that attacks it, because CSC operators, SCA field staff and SHG coordinators already have reach into this demographic.

Same engine, operator-shaped UI: "I'm helping someone else," batch intake, printable outputs, offline-tolerant. Also the BD channel — see `BUSINESS-PLAN.md`.

### 6.4 Voice

Two different things, and conflating them is a costly mistake.

**Voice notes on WhatsApp — MVP.** The user holds the mic and speaks; we transcribe, answer, and reply with spoken audio. Near-zero marginal cost, no telephony account, reuses the existing WhatsApp session and state machine. It solves the literacy problem for anyone holding a smartphone, which is the large majority of reachable users.

| Job | Model | Licence | Coverage |
|---|---|---|---|
| Speech → text | `ai4bharat/indic-conformer-600m-multilingual` | MIT | **all 22 scheduled languages** |
| Text → speech | `ai4bharat/indic-parler-tts` | open | 20 Indic + English |
| Translation bridge | IndicTrans2 | MIT | 22 languages |

One lab, three models, no vendor relationship, all self-hostable. Verified current 2026-09-03.

**Telephony IVR — Phase 3, deliberately.** Real inbound/outbound calling needs a telephony provider (per-minute cost), real-time ASR/TTS latency work, and a session model that differs from WhatsApp. Its justification is specific and real — **it is the only channel that reaches people with no smartphone at all**, which in this demographic is not a rounding error. But it is a live-demo risk (latency, call quality on stage, a telephony account to provision), and voice notes deliver most of the accessibility benefit for a fraction of the cost and risk. Build IVR when there's a funded pilot, not for a hackathon stage.

Voice is triggered automatically by the `education_status` signal (§5.2), not buried in a settings menu.

### 6.5 Region-aware multilingual

v2's rule was "language buttons, never auto-detection." That's right about *correctness* and wrong about *friction*. The fix isn't to pick one — it's **guess, then confirm in one tap**: pre-select the language we believe is right, still show the buttons.

**The signal cascade**, strongest first:

| Signal | Reliability | When |
|---|---|---|
| **PIN code → state → official language** | **highest** | once known — and we collect PIN for the locator anyway |
| WhatsApp location share → state | high | when shared |
| **Script detection on first message** | high | **immediately, free, deterministic** |
| Explicit button choice | absolute | always available, overrides everything |

**Script detection needs no model and no API** — Unicode block detection is a lookup. Tamil, Telugu, Kannada, Malayalam, Gujarati, Odia and Gurmukhi scripts each map to one language. Two are genuinely ambiguous — Devanagari (Hindi / Marathi / Konkani) and Bengali script (Bengali / Assamese) — and those are exactly where the PIN-code signal or the confirm tap resolves it. A user who types "नमस्ते" should never be asked to pick a language from a list in English.

**Phone number is not a location signal.** Indian mobile series were circle-allocated originally, but number portability broke that years ago. Don't use it; it will be confidently wrong.

**Which languages, in what order.** Not all 22 at once — promising 22 and shipping 2 is worse than shipping 4 well. Prioritise by **SC population by state**, which is published Census data, not a guess. That points at Hindi, Bengali, Tamil, Telugu, Marathi, Kannada and Punjabi first — and the resulting order is defensible to a judge because it's derived from the target demographic rather than from convenience. `TO VERIFY`: pull the exact state-wise figures before fixing the order.

**Translate at ingest, not at request.** Copy templates and Plane B blocks are stored per language in the corpus (`data-sources.md` §2.3), so the hot path never waits on a translation call. Only personalised numbers are generated live.

---

## 7. Feature catalogue

### 7.1 Eligibility & matching

| Feat | What |
|---|---|
| **Proof-Graded Eligibility** | Every result labelled VERIFIED / DECLARED / INFERRED (§5.2) |
| **No Dead Ends** | Out-of-category users routed to the right corporation, never rejected |
| **Train-then-Credit** | Project needs a skill the applicant lacks → NSFDC's own Skill Development Training first, credit after. Lending ₹1.4 L for a tailoring unit to someone who can't yet tailor manufactures an NPA. And this is not a consolation prize: the training is **free, NSQF-compliant, pays a ₹1,500/month stipend, and has no income ceiling at all** — so it's available even to people the loan schemes exclude. Protects the beneficiary; lower NPAs keep the partner prudentially eligible, so it feeds §7.4 |
| **Group Applications** | Partnership firms and cooperative societies are eligible if every member is SC and under the income ceiling — the SHG-adjacent path that matters in this demographic, and one v2 couldn't represent |
| **Right-Sizing** | Recommend what the project needs, not the ceiling. Over-borrowing is an NPA driver |
| **Why / Why-Not Trail** | Explains rejections, not just matches — see §7.2 |

### 7.2 Financial literacy — an explicit impact goal

Seven of eight are **deterministic templates, not generation**: cacheable, cheap, reliable, and consistent with the "eligibility is never the model's job" discipline.

| Feat | What |
|---|---|
| **True Cost Card** | Not the EMI — the total. *"You borrow ₹1,25,000. You repay ₹1,47,300 over 3 years. This loan costs you ₹22,300."* Most applicants never see that number before signing |
| **Moneylender Comparison** | The highest-impact screen in the product. The real alternative is not another bank — it's an informal lender at 3–10% *per month*. *NSFDC MFS @ 6.5%/yr → ₹22,300 interest. Local lender @ 5%/month → ₹1,87,500 on the same amount.* Literacy as a decision, not a lecture |
| **Moratorium in Cash-Flow Terms** | Nobody knows the word. A month strip: *months 1–3, ₹677 (interest only); from month 4, ₹3,842.* Plus the honest warning — a grace period is not free |
| **Repayment Reality Check** | *"Your EMI is ₹3,842/month. Your business must clear that after expenses. Will it?"* A feature that sometimes talks a user **out** of borrowing |
| **Jargon Decoder** | Tap any term — NPA, moratorium, collateral, tenure, principal, channel partner — in their language. Cached per (term × language) |
| **Why / Why-Not Trail** | *"You qualify for Micro Finance: ₹1.2 L project is under the ₹1.4 L ceiling, ₹2.8 L family income is under ₹5 L. You do not qualify for Term Loan — that starts at ₹1.4 L."* Explaining the rejections is what teaches the rules |
| **Fraud Shield** | *"NSFDC never charges a fee to apply. If anyone asks for money to process your loan, it's fraud."* Middleman extraction is endemic in this channel. See §10.2 for how this coexists with a paid service |
| **Cheapest Route** | *"That bank is 4 km away at 15%. This one is 11 km away at 13%. The extra 7 km saves you ₹— over your loan."* Same scheme, different partner, different price (§5.4). Nobody currently tells beneficiaries this, and it's the most concrete form financial literacy can take |
| **Ask Anything** | Open questions answered from official text with a citation — collateral, joint applications, missed payments, what if I have no shop yet. FAQ matches return the official answer verbatim; eligibility questions route to the deterministic engine, never to prose (§5.3) |
| **Priority Signals** | Women have a **40% fund-allocation target** under Term Loan and Micro Finance. If you're in a priority category, the product says so — that's actionable information nobody receives today |
| **Waiting-Period Micro-Lessons** | Three spaced WhatsApp messages during the dead time after submission: what to bring, what happens next, how repayment begins. Turns anxious silence into the one moment a user is receptive |

### 7.3 Faster disbursement — an explicit impact goal

Real causes of delay: incomplete applications, misrouting, document round-trips, no visibility, no accountability.

| Feat | What |
|---|---|
| **Zero-Rework Packet** | Completeness validated against *that partner's* checklist **before** submission. The top cause of delay is a bounced application. Headline metric: **first-time-right rate** |
| **One-Trip Promise** | When presence is mandatory (§9.1), make trip #1 succeed: pre-filled printable form, verified checklist, what to carry, which counter, which days. Today people make three or four trips; each is a lost day's wages plus fare |
| **AI Project Report (DPR)** | PM SURAJ requires a business plan — the hardest artifact in the stack for this user. The model drafts a document *from facts the user already gave*; it never decides eligibility |
| **Pre-Verified Facts** | A partner receiving DigiLocker-verified caste and income doesn't re-verify. Days out of the branch process |
| **SLA Clock** | Beneficiary sees status; partner sees an ageing queue; stalls past N days escalate to the SCA. Visibility alone accelerates institutions |
| **Document Pre-Fetch** | Start verification pulls while the user is still in conversation, not after |
| **Ground-Truth Loop** | One WhatsApp message post-visit, three buttons, 20 seconds: *was the branch where we said · did they process this scheme · did they ask for anything not on your list · how long has it been.* Corrects the corpus (§5.1) and supplies real disbursement timing **without needing a single partner to integrate first** — which is what makes the Flywheel below possible from day one |
| **Speed Flywheel** | Publish time-to-disburse per partner, feed it into `w5` of the routing score. Fast partners earn more volume. Converts speed from a hope into a system-wide incentive — a mechanism, not a feature |

Ground-Truth Loop safeguards, built in from the start: **N corroborating reports** before any rating moves (a single report never changes a partner's score); **aggregate only, never attributable**; integrity complaints routed to the formal grievance channel, never published; incentive is social (*"your report helped 12 people in your district"*), never cash — cash invites gaming.

### 7.4 Better fund utilisation — an explicit impact goal

| Feat | What |
|---|---|
| **Capacity-Aware Load Balancing** | Demand distributed in proportion to deployable headroom (§5.4) |
| **Idle-Fund Matching** | *"SCA X holds ₹Y undeployed; Z eligible applicants sit in its districts."* Pushed to the SCA. This is what the phrase literally means, and the published utilisation data supports it |
| **Coverage-Gap Map** | Demand origin vs. partner locations → districts with applicants and no viable partner. An artifact MoSJE would actually want |
| **Fiscal-Year Absorption Alerts** | Utilisation runs on an FY clock and the March rush is real. Flag under-deployed SCAs in Q2, while there's still time to deploy |
| **NPA Reduction by Design** | Train-then-Credit + Reality Check + Right-Sizing. **The PS's own prudential norms cut off fresh releases to partners with bad books — so reducing NPAs is mechanically identical to improving fund utilisation.** Say this loop out loud to a judge |

---

## 8. The verification ladder

Four rungs. Each independently shippable; each degrades gracefully to the one below. **Never a hard gate** — a user whose state has no DigiLocker integration must still get a full recommendation, labelled `DECLARED`.

| Rung | Mechanism | Proves | Licence | Status |
|---|---|---|---|---|
| **L0** | WhatsApp number possession | weak identity | none | built |
| **L1** | **Aadhaar Paperless Offline e-KYC** — user generates their own UIDAI-signed XML+ZIP, shares the code; we verify the XMLDSig against UIDAI's public certificate | name, DOB, gender, address — **cryptographically verified** | **none** (Offline Verification Seeking Entity, not an AUA) | **buildable now** |
| **L2** | **DigiLocker Requester API** — pull Caste + Income certificate | **SC status + income ≤ ₹5 L, legally verified under the IT Act** | Requester onboarding: registered entity, domain email, DSC | venture path |
| **L3** | Aadhaar authentication proper | full eKYC | AAGG Amendment Rules 2025 approval | strategic |

**L1 is the unlock most teams won't find.** Aadhaar Paperless Offline e-KYC requires no AUA/KUA licence — the user generates a UIDAI-digitally-signed XML themselves, and verifying that signature is pure Python against a public certificate. We never touch or store an Aadhaar number. Real, demonstrable, legally-grounded identity verification inside a hackathon build.

**L2 is where caste is actually proven**, and honesty matters here: caste and income certificates on DigiLocker depend on each state's e-District integration, and coverage is real but uneven. Design for partial coverage, not for the happy path.

**L3 is the sleeper, and it's a moat.** The *Aadhaar Authentication for Good Governance (Social Welfare, Innovation, Knowledge) Amendment Rules, 2025* (notified 31 Jan 2025) opened Aadhaar authentication to private entities for four listed purposes — one of which is verbatim **"prevention of dissipation of social welfare benefits."** The approval route is proposal → sponsoring ministry → MeitY. **The sponsoring ministry for this use case is MoSJE — the author of this problem statement.**

**One hard constraint:** Account Aggregator income verification is closed to us directly — FIU status requires RBI/SEBI/IRDAI/PFRDA regulation. Correct positioning is **Technology Service Provider to the partner lender**, who is the FIU. That's a feature for the business, not a limitation: it makes partner integration structural rather than optional.

---

## 9. Origination

### 9.1 `channel_capability` — the schema enforces honesty

Whether a scheme can be completed remotely is **a fact about each (scheme × partner type × state)**, not a judgement made per user. It lives in the corpus:

```
channel_capability = FULLY_REMOTE | HYBRID | PRESENCE_MANDATORY
```

**The product structurally cannot offer a service it can't deliver.** Where presence is mandatory, the assisted-filing option is never rendered — only the locator and the One-Trip Promise. This is not restraint we have to remember; it's the schema.

### 9.2 The two paths after a recommendation

```
Recommendation delivered  (always free)
        |
        +-- "Where do I go?"  -->  Map + partner list + directions        [FREE, always]
        |                          + One-Trip Promise pack               [FREE]
        |
        +-- "Help me apply"   -->  available ONLY if channel_capability
                                   != PRESENCE_MANDATORY
                                   |
                                   +-- Document checklist                [FREE]
                                   +-- Verification pull (L1/L2)         [FREE]
                                   +-- AI project report                 [FREE to view]
                                   +-- Assisted fill + verify + route    [PAID, §10.2]
```

### 9.3 Packet contents

Verified identity facts (with proof grades) · caste & income certificates where available · project report · document checklist status · scheme match with the Why trail · routing decision with its justification · corpus version.

Routed to a **channel partner**, never to NSFDC (§1.4). Partner accepts, requests a missing document, or declines with a reason — every outcome feeds the SLA clock and the Speed Flywheel.

---

## 10. Commercial rules that constrain the product

Full model in `BUSINESS-PLAN.md`. Two rules bind the *product* and belong here.

### 10.1 Permanently free, no exceptions
Eligibility · EMI and True Cost · every financial-literacy feature · partner locator and maps · document checklist · the One-Trip Promise pack.

A platform for SC beneficiaries under ₹5 L income that paywalls its core would deserve the criticism it got. Only **assisted filling + verification** is ever paid.

### 10.2 The Fraud Shield tension, resolved

Feat 7 says *"NSFDC never charges a fee to apply."* We then charge for assistance. Someone on the panel will put those two side by side, and fine print won't survive it. It resolves only with precision:

> The government charges ₹0. **You can do all of this yourself for free — here's exactly how.** We charge ₹X only if you'd like us to fill and verify it for you.

Showing the free path with **equal prominence** turns the contradiction into a trust signal. Precedent exists: CSCs charge notified service fees for e-governance services, and nobody calls that fraud, because the free path stays open and visible.

**Payer waterfall — the beneficiary is the last payer, not the first:**
1. CSR sponsor (`BUSINESS-PLAN.md`)
2. Partner lender origination fee
3. SCA / corporation B2G contract
4. Beneficiary convenience fee — last resort, capped, waivable

---

## 11. Non-functional

**Reliability** — inherited unchanged from v2 and non-negotiable: async webhook (verify → idempotency check → enqueue → 200, no slow work in the handler, ever), atomic state via LangGraph checkpointer, every worker step idempotent and retryable. These fixed real prior failures; do not regress.

**Data protection (DPDP)** — caste is high-sensitivity personal data; income and Aadhaar-adjacent fields critical-sensitivity. Itemised consent before collection, data minimisation, encryption at rest, a real deletion path, easy withdrawal. The DPDP Rules were notified 13 Nov 2025 on a staged rollout with substantive obligations effective 13 May 2027 — this is compliance-by-design ahead of a dated deadline, which is a stronger position than a vague grace period. Verification adds obligations: **never store an Aadhaar number** (L1 is designed so we never receive one), store certificate *assertions* rather than document copies wherever the flow permits.

**Ground-truth data** — aggregate-only, corroboration-thresholded, never attributable (§7.3).

**Security** — webhook signature verification, no key in the public repo, per-user and per-endpoint rate limiting, all webhook input validated.

**Cost** — ₹0 to build and demo. SQLite, Gemini free tier, OpenRouter free models (ZDR endpoints only), IndicTrans2 self-hosted, Leaflet/OSM/OSRM, Twilio Sandbox.

**Auditability** — every recommendation reproducible from its corpus version and rule trace. Required for a welfare product, and it's the measurability CSR buyers pay for.

---

## 12. Build phases and the fallback order

Three surfaces are being built. **The risk is arriving at internals with three half-finished ones**, so the order below is a strict priority ladder: each rung must be demo-ready before the next gets time.

| Rung | Scope | Rationale |
|---|---|---|
| **0** | v2 Phase 0–3 (built, 72 tests) | The safety net. Do not regress |
| **1** | **The PS's three named deliverables, fully right** — Plane A corpus (5 schemes, dual rates, quarterly repayment, applicant types), 148-activity taxonomy for Tier 2, `education_status`, family-income fix, instalments across all bands, map integration, prudential routing on real published data | This alone is a complete, defensible PS answer. `rules.md`'s own advice: get the named things right before reaching for more |
| **2** | Plane B corpus + **Ask Anything** + financial literacy (§7.2) + Why/Why-Not trail + Cheapest Route | Cheapest points on the board — mostly ingestion and deterministic templates, against an explicit impact goal. Plane B is one scraping pass over pages we've already located |
| **3** | L1 verification (Aadhaar Offline e-KYC) + proof grading | The differentiator. Buildable with no licence |
| **4** | Partner console — read-only queue + prudential status + Coverage-Gap Map | Makes the two-sided story live rather than theoretical |
| **5** | L5 origination — checklist, DPR, packet, One-Trip Promise | The extension. Defensible via "Router," but it is an extension |
| **6** | Assisted mode + Ground-Truth Loop | Distribution and the data moat |
| **7** | Voice/IVR, multi-corporation population, L2 DigiLocker | Nationals and beyond |

**If time compresses, cut from the bottom.** Rungs 0–2 are a complete PS answer on their own.

Two habits from v2 worth restating: deploy to a real host early rather than demoing off `localhost`, and stop writing new code with real buffer time before any deadline — that time is worth more spent rehearsing the demo and fixing what breaks live.

---

## 13. Success metrics

**Product** — first-time-right rate (packets accepted without a document request) · median time from first message to routed packet · median time-to-disbursement by partner · proportion of results at `VERIFIED` grade · trips per successful application (target: 1).

**Impact** — beneficiaries reaching a correct scheme match who had never heard of it · literacy-feature engagement · ₹ credit unlocked · districts covered · **idle funds deployed** via idle-fund matching.

**Demo-day** — a judge can send a WhatsApp message and reach a routed, verified, complete packet; boundary income of exactly ₹5,00,000 behaves correctly; an out-of-category profile hits No Dead Ends instead of a wall.

---

## 14. Risks and open questions

| Risk | Response |
|---|---|
| Three surfaces, one team | Strict fallback ladder (§12). Rungs 0–2 are a complete answer |
| Scheme numbers still shift | Corpus is provenance-stamped and versioned; changing a rate is a data edit, not a code change |
| DigiLocker coverage is state-patchy | Ladder degrades to `DECLARED`, never gates (§8) |
| Utilisation data is periodic, not real-time | State it plainly — monthly published data is a large upgrade on mocked data, and the Ground-Truth Loop adds a live signal |
| Fee optics | §10.2, and the payer waterfall puts the beneficiary last |
| Ground-truth gaming | Corroboration thresholds, aggregate-only, social not cash incentive |
| Scope creep into a lending product | We never lend, never decide credit, never take custody of funds. We originate and route |

**Resolved since v2, with sources** (`data-sources.md` §4): the rate range was a wrong-model problem, not a source conflict · the income ceiling is **₹5 L, rural and urban, effective 2026-01-07** — the ₹3 L/₹3.5 L figures everywhere online are simply stale · no age criterion exists, so v2's removal of age fields is confirmed rather than assumed.

**Still open, needs a human, not more research:** a twenty-minute eyeball confirmation of the corpus on the live NSFDC pages before the finale (it was retrieved by automated fetch) · security/collateral requirements, which aren't published anywhere we've found · `channel_capability` per state, which has no published source and starts at the conservative `PRESENCE_MANDATORY` default · MUJ submission rules and the AI-narration policy · whether Twilio Sandbox or Meta Cloud API is the demo path.
