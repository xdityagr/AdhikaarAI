# Yojna Setu — SIH 2026 submission report

**PS26092 · AI-Driven Scheme Matching for Marginalized Entrepreneurs**
Ministry of Social Justice & Empowerment · Category: Software · Theme: Smart Automation

> **On the numbers in this document.** Every figure is either `[VERIFIED]` with the
> source and the date it was read, or marked `[PLANNED]`/`[TO VERIFY]`. Nothing is
> estimated and presented as fact. This project has twice been burned by
> confident-sounding invented statistics, so the discipline is deliberate — and
> being able to say it out loud is itself part of the pitch.
>
> Companion documents: `PRD-v3.md` (product spec) · `BUSINESS-PLAN.md` (market and
> model) · `data-sources.md` (every source with confidence tags) · `MVP-PLAN.md`
> (build status and the 4-minute demo script).

---

## 1. The problem

NSFDC lends to Scheduled Caste borrowers at **6.5% a year** — below any commercial
rate in India, financing up to 90% of a project. Almost nobody who qualifies knows
it exists.

The problem statement names the mechanism precisely: money does not go direct.
It flows through a **Channel Finance System** of 100+ partners — State
Channelizing Agencies, public sector banks, RRBs, NBFC-MFIs. `[VERIFIED: NSFDC
FAQ states 102 partners across 8 categories]` That structure creates four failures,
all of which the PS names:

1. **Nobody knows which scheme fits.** The PS names three products. NSFDC actually
   publishes five, at rates from 6.5% to 15%.
2. **Nobody can find an authorised partner** for their scheme and location.
3. **Applications are misrouted** to partners who cannot currently disburse.
4. **The credit channel is invisible.** India's flagship credit portal,
   JanSamarth, carries 15 schemes and 269 partner banks — and **zero** NFDC
   products. `[VERIFIED: financialservices.gov.in/jansamarth]` Not an oversight:
   JanSamarth is built for direct bank lending, and these lend through SCAs. The
   plumbing does not match, so the whole channel was left out.

And underneath all of it, a harder problem the PS's impact goals point at: a
household needing a **pension, a scholarship, a house, or medical help** has no
single place to ask either. Credit is one thread of a much larger tangle.

### Who we are building for

A daily-wage earner for whom **every branch visit costs a day's wages plus bus
fare**. Possibly not literate in English, possibly not literate at all. Owns a
low-end Android phone with WhatsApp. Whose actual alternative to a 6.5% government
loan is a moneylender at **3–10% per month**.

That single fact — the cost of a wasted trip — drives more design decisions in
this project than any other.

---

## 2. The solution

**Yojna Setu is the origination layer for India's social-justice welfare channel.**

Not a chatbot and not a scheme directory. The rail between a beneficiary and an
office that can actually pay them.

> Every other platform tells you which scheme you *might* qualify for. Yojna Setu
> proves you qualify, tells you what the loan actually costs against the
> moneylender you would otherwise use, and routes you to a partner who can
> disburse this month — in your own language, in your own script.

### What it does

| | |
|---|---|
| **Finds every scheme you qualify for** | Not just credit. Housing, pensions, scholarships, health, disability — across all 15 government welfare categories, filtered to what a marginalised household is actually eligible for |
| **Explains the misses** | You are told which schemes you did *not* qualify for and exactly which threshold you missed. Explaining rejections is what teaches people the rules |
| **Prices it honestly** | The real quarterly instalment (NSFDC does not repay monthly), a monthly figure to budget against, and the total the loan costs over its life |
| **Compares to the real alternative** | ₹12,568 under the scheme against ₹1,78,200 from a moneylender, on the same ₹1.08 lakh `[VERIFIED: computed by the code, not written for a slide]` |
| **Routes to a partner who can pay** | Prudential filtering on NSFDC's own published fund data, with the exclusion reason shown in plain language |
| **Proves who you are** | Aadhaar offline e-KYC verified against UIDAI's signature — no licence required |
| **Follows through** | Application timeline, guided handoff to the official status checkers, and grievance escalation when it stalls |

### Where it meets people

**WhatsApp** (zero install, works on any phone) and a **web app** — both driven by
one shared engine, so the two channels cannot disagree about who qualifies.

---

## 3. Technical approach

### 3.1 The architecture

```
        WhatsApp (Twilio)          Web (Next.js)
                 \                    /
                  \                  /
              ┌──── FastAPI · one shared engine ────┐
              │  eligibility · calculator ·         │
              │  literacy · routing · verification  │
              └──────────────┬──────────────────────┘
                             │
              corpus: NSFDC (deep) + myScheme (broad)
```

Python/FastAPI holds the engine; Next.js + Tailwind + shadcn/ui is the web
frontend, proxying `/api/*` to FastAPI so the browser sees one origin and there is
no CORS. WhatsApp runs on LangGraph with a SQLite checkpointer.

### 3.2 The rule that shapes everything: eligibility is never the model's job

An LLM must never decide whether someone qualifies for a loan. The engine is a
deterministic rules evaluation over typed numeric thresholds, boundary-exact —
family income of exactly ₹5,00,000 qualifies, ₹5,00,001 does not, every time.

The corpus is split into two planes to make that rule enforceable rather than
aspirational:

- **Plane A — structured.** Typed numbers and enums. Feeds eligibility, the
  calculator and the router. Never touched by a model.
- **Plane B — narrative.** Purpose, benefits, documents, FAQs. Retrieved and
  quoted by the assistant, and it **never decides**.

A Plane B hallucination therefore cannot produce a wrong eligibility verdict. And
every rupee figure a borrower sees comes from a deterministic template
(`src/literacy.py`), not from generation — so no number on screen can be invented.

### 3.3 The data spine

**Tier 1 — NSFDC, full depth.** Five schemes, hand-reviewed, git-tracked with
per-field provenance (source URL, fetch date, confidence). Cost modelling,
prudential routing, partner locator, identity verification.

**Tier 2 — myScheme, national breadth.** `[VERIFIED 2026-09-07: api.myscheme.gov.in
returns total 4772]` All 4,772 central and state welfare schemes, with **official
government translations** in Hindi, Tamil, Bengali and Marathi — so scheme content
is never machine-translated.

**The finding that makes Tier 2 work.** myScheme's `lang=en` response returns
eligibility as **prose only** (2 fields). The same scheme under `lang=hi` returns
**24 structured fields** — caste as machine values `["sc"]`, `familyIncomeAnnual
{gte, lte}`, age bands, isBpl, occupation, residence, beneficiaryState. Only the
labels are translated; the values are stable machine strings. `[VERIFIED live on
dls-punjab and pm-kisan, 2026-09-07]`

That turns "match 4,772 prose rules" into the same deterministic numeric matching
the NSFDC engine already does. It is almost certainly a bug in their API, so we
depend on it defensively: an independent facet index cross-checks it, the raw
object is stored verbatim so a built corpus keeps working, and a test asserts the
quirk still holds.

**Two traps in that data, both found by testing rather than reading:**

- **Facet values are full label strings.** `"Scheduled Caste (SC)"`, not `"SC"`.
  A wrong value returns **HTTP 200 with zero results and no error** — so one
  typo ships a corpus containing no SC schemes at all. Values are read from the
  API's own facet block, never hardcoded, and expected counts are asserted.
- **Absence is not negation.** `isBpl: null` means the scheme does not say — not
  "No". `caste: ["All"]` means open to everyone. Naively filtering caste = SC
  returns 394 schemes and hides the 4,001 open to all, so an SC user would see
  394 instead of ~4,395. Matching is inclusive-by-default: a facet excludes only
  when the scheme *specifically names* values and the user is not among them.

**Honesty in the verdict.** NSFDC schemes return `ELIGIBLE` — every published rule
is evaluated. Every myScheme result returns at most `LIKELY`, with copy saying so.
Promising eligibility across 4,772 prose rules nobody has read would be the most
damaging thing this project could ship.

### 3.4 Real data where everyone else mocks it

The prudential routing rules are public: an SCA needs 100% cumulative utilisation
and zero overdues; an RRB needs net NPA below 15%. The assumption is that the
*data* is internal to NSFDC.

**It is published.** `[VERIFIED: nsfdc.nic.in/performance-data]` NSFDC releases
state-wise cumulative fund utilisation as Excel, current to **31 July 2026**. The
ingest parses 36 states × 9 financial years. For FY2025-26, **11 of 36 states meet
the 100% norm and 25 do not** — so both a routable partner and an excludable one
exist in the real data.

Two parser bugs were found only by running it against the real file: the title row
contains both header keywords so a substring match selected it as the header, and
the sheet stacks several tables with different layouts so reading to end-of-file
produced 135 "states" per year. A self-consistency guard now drops any row where
the published percentage disagrees with actual/allocation.

### 3.5 Identity verification without a licence

Aadhaar *authentication* requires AUA/KUA onboarding. **Paperless Offline e-KYC is
a different mechanism**: the resident downloads their own UIDAI-signed XML and
supplies a share code. Verifying that signature makes us an Offline Verification
Seeking Entity — no licence, no onboarding, and the file contains **no Aadhaar
number**, only the last four digits.

Full enveloped XMLDSig verification, implemented directly with `cryptography` and
`lxml`: canonicalise the document with the signature removed, SHA-256 it, compare
to `DigestValue`, then RSA-verify `SignatureValue` over the canonicalised
`SignedInfo`. **Both halves matter** — checking only the signature lets someone
swap the document body; checking only the digest lets them forge it outright. The
tests build a genuinely RSA-signed document and prove that altering the name or
the address is caught.

It grades `VERIFIED` / `DECLARED` and **never gates**: an unverified user gets the
identical recommendation.

### 3.6 Language

Five languages — Hindi, English, Marathi, Bengali, Tamil — chosen by SC population
rather than convenience. **Script detection is a Unicode lookup, not a model**, so
typing `मुझे सिलाई की दुकान खोलनी है` switches the entire app to Hindi from the
first message, with no language menu in English first.

Two rules: **numbers are never translated, only formatted**, so a translation bug
cannot change what a loan costs. And **scheme names stay in English**, because
that is what is printed on the form at the counter.

### 3.7 Stack

Python 3.13 · FastAPI · LangGraph · SQLite (WAL) · Pydantic · httpx · pandas ·
pdfplumber · Pillow · cryptography · lxml · Next.js · Tailwind · shadcn/ui ·
Twilio WhatsApp · OpenStreetMap · Gemini (generation only, never eligibility).

**221 tests passing.** `[VERIFIED 2026-09-07]`

---

## 4. Feasibility and viability

### 4.1 It costs ₹0 to build and demo

SQLite, Gemini free tier, OpenStreetMap with a local tile cache, Twilio's free
sandbox (**$15 credit + 100 free WhatsApp messages** `[VERIFIED]`), self-hosted
open models. No paid API is required for anything demonstrated.

### 4.2 What needs no permission — and what does

| Capability | Status |
|---|---|
| Scheme corpus, all 4,772 | **Working.** Public government API |
| NSFDC fund-utilisation routing | **Working.** Published Excel |
| Aadhaar offline e-KYC | **Working.** No licence — OVSE, not AUA |
| WhatsApp delivery | **Working.** Twilio sandbox |
| Caste/income certificate pull | Needs DigiLocker Requester onboarding — registered entity, domain email, DSC |
| Aadhaar authentication proper | Needs AAGG Rules 2025 approval, sponsored by a ministry |
| Automated payment status | **Impossible for anyone.** See §4.3 |

The verification ladder degrades gracefully: each rung is independently useful and
an unverified user is never blocked.

### 4.3 The tracker: what we cannot do, and why saying so is a strength

We researched whether a third party can check a citizen's welfare payment status.
**It cannot be done — by anyone.** `[VERIFIED]`

- **PFMS** has no public API and actively blocks automated clients (HTTP 400,
  "Unauthorized Request Blocked"). Its citizen lookups are captcha- and OTP-gated.
- **DBT Bharat**'s API is write-only, aggregate-only, IP-whitelisted, with a
  per-scheme encryption key. States push; nobody reads.
- **API Setu** publishes no payment-status or scheme-status API at all.
- **Account Aggregator** requires FIU status, which requires RBI/SEBI/IRDAI/PFRDA
  regulation.
- For NSFDC there is **no central record to read**. Their own FAQ: *"Direct
  contact or correspondence by the Applicants/Beneficiaries shall not be
  entertained by NSFDC under any circumstances."* Money flows NSFDC → SCA →
  beneficiary; only the branch knows.

So the tracker is a **guided handoff, a self-reported timeline, and escalation** —
and the schema records `source: SELF_REPORTED` on every row so the interface can
never imply otherwise. A tracker that looked like it was polling government
systems when it was not is the one feature here that could genuinely harm someone:
they would stop chasing their SCA because our screen said "in progress".

What we *can* remove is the real barrier — navigating PFMS's captcha-gated ASPX
pages in English. One tap into the right official checker, step-by-step in their
language, the PFMS error code decoded, and when it stalls: a drafted CPGRAMS
grievance, the state DBT cell, and the PFMS helpdesk.

### 4.4 Business viability

Full detail in `BUSINESS-PLAN.md`. In short:

**Free forever for the beneficiary** — eligibility, cost, literacy, locator,
checklist. A platform for SC households under ₹5 lakh income that paywalled its
core would deserve the criticism.

Revenue from the three actors with budgets: **partner origination fees** (they
receive a pre-verified borrower), **B2G licences** to SCAs and corporations for the
console and utilisation intelligence, and **CSR sponsorship** — Schedule VII of the
Companies Act expressly covers *"measures for reducing inequalities faced by
socially and economically backward groups"* `[VERIFIED: Companies Act 2013 s.135]`.
The sharpest target is banks and NBFCs, who carry CSR obligations *and*
priority-sector lending targets, and can satisfy both from the same rupee.

### 4.5 Scale

**One engine serves six corporations.** NSFDC (SC), NSTFDC (ST), NBCFDC (OBC),
NSKFDC (safai karamcharis), NMDFC (minorities), NHFDC (disability) all run the same
SCA channel-finance structure. The eligibility rules differ; the architecture does
not. PM SURAJ already unifies three of them, so the government itself treats this
as one addressable channel.

---

## 5. Why us

Seven things, each checkable.

**1. We read the source, not the brief.** The PS names three schemes. NSFDC
publishes five. The PS's own quoted range — *"6.5% to 15% depending on the
scheme"* — is arithmetically impossible with three products, and its *"3 to 12
months"* moratorium range likewise. Both reconcile exactly with five. Our own
planning documents had spent five research passes treating this as irreconcilable
source conflict; it was a wrong-model problem, and reading the primary source
resolved it.

**2. Our prudential routing runs on real published data.** Everyone assumes NSFDC's
fund-utilisation figures are internal. They are published as a spreadsheet, and we
parse it. Real rule, real numbers, monthly refresh.

**3. Eligibility is proven, not asserted.** Cryptographic verification against
UIDAI's own signature, with no licence, and no Aadhaar number ever touched.

**4. We explain the rejections.** *"Term Loan starts at ₹1.40 lakh — your project
is ₹1.20 lakh."* Explaining the misses is what actually teaches someone the rules,
and it is the PS's financial-literacy impact goal made concrete.

**5. We price against the real alternative.** Not another bank — a moneylender at
5% a month. ₹12,568 against ₹1,78,200 on the same money. That comparison is the
moment a concessional rate stops being an abstraction.

**6. We tell you which door is cheaper.** Udyam Nidhi costs 13% through a
cooperative bank and 15% through a small finance bank — same scheme, same
borrower, different price. And at ₹1.2 lakh a person qualifies for Micro Finance at
6.5% *and* Aajeevika at 15%: **₹29,389 apart on an identical project.** Nobody
tells them.

**7. We are honest about what is mocked.** Branch-level NPA figures are
representative, because no public source publishes them — and the app says so on
every response. That is a research finding, not a gap, and volunteering it reads
as rigour where being caught on it would not.

### What went wrong, and what we did about it

Asked what broke, we have specific answers rather than a shrug. Seven real bugs,
each found by running the thing rather than reading it:

- The app **could not start** — `AsyncSqliteSaver.from_conn_string()` returns an
  async context manager, not a saver. Unit tests stubbed the checkpointer, so
  nothing caught it until the server ran for real.
- **Business loans were offered to education applicants** — project types lived in
  a module-level dict and a missing entry matched *everything*.
- **Quarterly loans were priced monthly**, and every scheme used one global tenure.
- A single message **contradicted itself twice** — the intro quoted a 6-month grace
  and `rate_max` while the block below said 3 months and used `rate_min`.
- **Men were quoted the women's rebate.**
- A Ballia applicant was **routed to the Bihar agency** — an SCA channels funds
  within its own state.
- **The prudential rule was inverted.** Low utilisation was excluding agencies, but
  an agency below 100% is by definition holding undeployed funds. The PS names its
  exclusion criteria as *"high NPAs or overdues"* — not low utilisation — and
  excluding idle-fund agencies is the exact opposite of the fund-utilisation goal.

---

## 6. Impact

**Financial literacy** — the True Cost card, the moneylender comparison, the
moratorium explained in cash-flow terms, the jargon decoder, the why-not trail,
and a fraud shield stating that NSFDC never charges a fee to apply. Seven of eight
are deterministic templates, so they are free to run and cannot hallucinate.

**Faster disbursement** — completeness validated against the partner's own
checklist before submission, because the top cause of delay is a bounced
application. The headline metric is **first-time-right rate**, and the target for
trips per successful application is **one, not four**.

**Better fund utilisation** — demand routed toward agencies holding undeployed
funds, coverage-gap maps showing districts with applicants and no viable partner,
and NPA reduction by design: right-sizing loans and routing people to free
NSQF-certified skill training *before* credit where the skill is missing. Since
the prudential norms cut off fresh releases to partners with bad books, **reducing
NPAs is mechanically identical to improving fund utilisation.**

---

## 7. Research and references

Everything below was fetched and verified. Full confidence tags per source in
`data-sources.md`.

### Primary — NSFDC
- Schemes (5 products, dual rates, quarterly repayment) — `nsfdc.nic.in/scheme`
- Eligibility, income ceiling ₹5L rural+urban **effective 7 Jan 2026** —
  `nsfdc.nic.in/eligibility-requirements`
- 148 fundable activities in 3 sectors — `nsfdc.nic.in/indicative-activities`
- 102 partners, women's 40% allocation, free NSQF training with ₹1,500/month
  stipend — `nsfdc.nic.in/faqs`
- **State-wise cumulative fund utilisation, to 31 Jul 2026** —
  `nsfdc.nic.in/performance-data`
- Partner directory, 8 categories — `nsfdc.nic.in/our-channel-partners`

### National scheme data
- **myScheme API** — `api.myscheme.gov.in`, 4,772 schemes, 15 categories,
  22 eligibility facets, official translations
- PM SURAJ, unified applications for NSFDC/NBCFDC/NSKFDC — `pmsuraj.dosje.gov.in`
- JanSamarth, 15 schemes / 269 banks / zero NFDC — `financialservices.gov.in/jansamarth`

### Identity and verification
- Aadhaar Paperless Offline e-KYC (OVSE, no licence) — UIDAI
- DigiLocker Requester API — `apisetu.gov.in/digilocker`
- **Aadhaar Authentication for Good Governance (Amendment) Rules 2025**, notified
  31 Jan 2025 — lists *"prevention of dissipation of social welfare benefits"* as a
  permitted purpose for private entities, approved via the sponsoring ministry

### Payment and grievance
- PFMS DBT Status Tracker — `pfms.nic.in/SitePages/DBT_StatusTracker.aspx`
- PFMS helpdesk — 1800 118 111 · `helpdesk-pfms@gov.in`
- State DBT cells — `dbtbharat.gov.in/dbtcell/state-list`
- CPGRAMS — `pgportal.gov.in`

### Regulatory
- Companies Act 2013 **s.135** — CSR applicability (net worth ≥ ₹500 cr, *or*
  turnover ≥ ₹1,000 cr, *or* net profit ≥ ₹5 cr; 2% of 3-year average net profit)
  and **Schedule VII**, which expressly covers backward groups and SC/ST welfare
- **DPDP Rules**, notified 13 Nov 2025, substantive obligations from 13 May 2027 —
  caste is high-sensitivity personal data, and this is compliance-by-design ahead
  of a dated deadline
- Account Aggregator — FIU status requires RBI/SEBI/IRDAI/PFRDA regulation

### Open models (specified, not yet built)
- `ai4bharat/indic-conformer-600m-multilingual` — speech-to-text, all 22 scheduled
  languages, MIT
- `ai4bharat/indic-parler-tts` — speech synthesis, 21 languages
- `AI4Bharat/IndicTrans2` — translation bridge, MIT

---

## 8. Status, plainly

**Working and tested (221 tests):** the 5-scheme corpus with provenance · NSFDC
fund-utilisation ingest · deterministic eligibility with why-not reasons ·
quarterly calculator · literacy templates · prudential routing · map rendering ·
Aadhaar XMLDSig verification · WhatsApp end to end · five-language script detection
· the myScheme ingest with structured-eligibility parsing.

**In progress:** the full 4,772-scheme corpus build · the Next.js frontend ·
the tracker.

**Specified, not built:** voice (models chosen) · DigiLocker certificate pull ·
assisted CSC mode · the other five corporations · telephony IVR.

**Known gaps:** branch-level NPA figures are representative and labelled as such ·
the partner console needs rebuilding after a frontend change dropped it · the UI
has not yet been reviewed on a real device.
