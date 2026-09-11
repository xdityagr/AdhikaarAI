# Data Sources & Corpus

**Every fact the system reasons over, with where it came from and how much to trust it.**
Companion to `PRD-v3.md` (§5.1 L1 Corpus) and `BUSINESS-PLAN.md`.

> **Supersedes `rules.md` on scheme numbers and eligibility.** `rules.md` concluded the NSFDC figures "hadn't converged and won't." §2.1 explains why they had converged, and §4.2 resolves the income-ceiling conflict outright — with a date. Keep `rules.md` for the team/process facts; treat this file as authoritative for the corpus.

## Confidence vocabulary

| Tag | Meaning |
|---|---|
| `OFFICIAL` | Fetched from the issuing body's own site. Date recorded |
| `PS-STATED` | Stated in the problem statement. Authoritative for judging regardless of reality |
| `DERIVED` | Computed from `OFFICIAL` data. Reasoning shown |
| `MOCKED` | Placeholder. Real rule, synthetic value. **Must be disclosed in-product, not just in docs** |
| `TO VERIFY` | Not yet obtained. Method recorded |

---

## 1. Source registry

All fetched **2026-09-03** unless noted.

### 1.1 NSFDC — primary

| # | URL | What we take | Format | Confidence |
|---|---|---|---|---|
| 1 | `/scheme` | 5 schemes: ceilings, **dual rates**, tenure, moratorium, **repayment frequency** | HTML | `OFFICIAL` |
| 2 | `/eligibility-requirements` | Category, **income ceiling + effective date**, **applicant types** | HTML | `OFFICIAL` |
| 3 | `/indicative-activities` | **148 fundable activities across 3 sectors** | HTML | `OFFICIAL` |
| 4 | `/faqs` | FAQ pairs, partner count, women's allocation, skill-training terms, helpline | HTML | `OFFICIAL` |
| 5 | `/how-to-apply-2` | Application process narrative | HTML | `TO VERIFY` — not yet fetched |
| 6 | `/form` | Downloadable application forms | PDF | `TO VERIFY` — not yet fetched |
| 7 | `/allocation-of-funds` | Fund allocation guidelines | HTML | `TO VERIFY` — not yet fetched |
| 8 | `/our-channel-partners` | Partner directory, **8 categories** | PDF per category | `OFFICIAL` |
| 9 | `/performance-data` | 9 datasets incl. **state-wise cumulative funds utilisation** (to 2026-07-31), channel-partner-wise disbursement | **Excel + PDF** | `OFFICIAL` |
| 10 | `/skill-development-training-programmes` | Training programmes (Train-then-Credit) | HTML | `OFFICIAL` |
| 11 | `/contact-us`, `/head-office-liaison-centre` | HQ + 4 liaison centres, **helpline 1800110396** | HTML | `OFFICIAL` |
| 12 | `/annual-reports`, `/mou` | Policy documents, historical figures | PDF | `TO VERIFY` |

### 1.2 Other corporations and national rails

| # | Source | What | Confidence |
|---|---|---|---|
| 13 | PM SURAJ — `pmsuraj.dosje.gov.in` | Application rail for NSFDC + NSKFDC + NBCFDC; document requirements | `OFFICIAL` — login-walled beyond landing |
| 14 | NBCFDC — `nbcfdc.gov.in`, `/web/hi/sca`, `/nbcfdcdashboard` | OBC schemes, SCA list, dashboard | `OFFICIAL` |
| 15 | NSKFDC — `nskfdc.nic.in` | Safai Karamchari schemes | `TO VERIFY` — host refused connection 2026-09-03; retry |
| 16 | NSTFDC / NMDFC / NHFDC | ST / minority / disability schemes | `TO VERIFY` — Phase 4 |
| 17 | myScheme — `myscheme.gov.in` | 4,700+ central & state schemes; **the national section schema** (§2.2) | `OFFICIAL` — client-rendered |
| 18 | API Setu — `directory.apisetu.gov.in/api-collection/myscheme` | myScheme APIs, OAS 3.0 | `OFFICIAL` — collection exists; **endpoints `TO VERIFY`** |
| 19 | DigiLocker — `apisetu.gov.in/digilocker` | Caste + income certificate pull | `OFFICIAL` — see §6 |
| 20 | India Post PIN codes | PIN → coordinates fallback | `TO VERIFY` — pick a mirror |
| 21 | OpenStreetMap / OSRM | Map tiles, road distance | `OFFICIAL` — free, no key |
| 22 | State SCA sites | Branch addresses, state-specific rules | `TO VERIFY` — highest-effort, highest-moat |

`india.gov.in` was reviewed and **is not a source** — it's a directory linking onward to the above. Ingest the primaries; skip the index.

---

## 2. Schema

### 2.1 Why the old schema was wrong

v3's first draft modelled a scheme as **eleven numeric fields**. That is an eligibility calculator's schema, and it throws away most of what's on the page.

The real pages carry purpose, eligibility narrative, an official 148-item activity taxonomy, application routes, document lists, FAQ pairs, downloadable forms, contact channels and a helpline. An assistant that can only answer *"are you eligible and what's the EMI"* is a calculator with a chat interface. A beneficiary's actual questions are *"what papers do I need," "do I need collateral," "can my wife and I apply together," "what if I have no shop yet," "who do I call."*

### 2.2 Two planes, and the wall between them

The schema splits by **how a field may be used**, which is the safety property that matters:

| Plane | Content | Consumed by | Rule |
|---|---|---|---|
| **A — Structured** | typed numbers, enums, booleans | Tier 1 eligibility, calculator, router | **Deterministic. Never LLM-touched** |
| **B — Narrative** | prose: purpose, benefits, eligibility text, process, documents, FAQs | Retrieval → LLM Q&A | **LLM may quote it; never decide from it** |
| **C — Assets** | forms, guidelines, circulars | Served as links/downloads | Cached, checksummed |

**The wall is the whole discipline.** The model may answer *"what documents do I need?"* from Plane B. *"Am I eligible?"* is only ever Plane A. This preserves v2's "eligibility is never the model's job" rule while making the assistant genuinely conversational — and it means a Plane B hallucination can never produce a wrong eligibility verdict.

Plane B sections mirror **myScheme's national taxonomy** (Details · Benefits · Eligibility · Application Process · Documents Required · FAQs · Sources & References) — MeitY's de facto standard across 4,700+ schemes. Mirroring it buys interoperability now and lets us ingest myScheme wholesale in Phase 4 without a migration.

### 2.3 The schema

```python
Scheme = {
  # ---- identity -------------------------------------------------------
  "scheme_code": "NSFDC_UDYAM_NIDHI",
  "corporation": "NSFDC",            # NSFDC|NBCFDC|NSKFDC|NSTFDC|NMDFC|NHFDC
  "name": {"en": "Udyam Nidhi Yojana", "hi": "..."},
  "short_name": "UNY",
  "status": "ACTIVE",                # ACTIVE|SUSPENDED|CLOSED
  "corpus_version": 7,
  "provenance": {"source_url": "...", "fetched_at": "2026-09-03", "confidence": "OFFICIAL"},

  # ---- PLANE A: structured, deterministic -----------------------------
  "eligibility": {
      "category": ["SC"],
      "applicant_types": ["INDIVIDUAL", "PARTNERSHIP_FIRM", "COOPERATIVE_SOCIETY"],
      "all_members_must_qualify": True,      # partnerships/co-ops
      "max_family_income": 500_000,
      "income_basis": "ANNUAL_FAMILY_ALL_SOURCES",
      "income_effective_date": "2026-01-07",
      "income_applies_to": ["RURAL", "URBAN"],
      "age": None,                            # not published — see 4.3
      "requires_caste_certificate": True,
  },

  "finance": {
      "max_project_cost": 500_000,
      "max_loan": 450_000,
      "financing_pct": 0.90,
      "intermediary_rate": 5.0,               # NSFDC -> channel partner
      # BENEFICIARY RATE VARIES BY PARTNER TYPE. See 3.2 — this is routing-relevant.
      "beneficiary_rate_by_partner_type": {
          "COOPERATIVE_BANK": 13.0,
          "COOPERATIVE_SOCIETY": 13.0,
          "SMALL_FINANCE_BANK": 15.0,
      },
      "tenure_years": 5,
      "repayment_frequency": "QUARTERLY",     # NOT monthly — see 3.1
      "moratorium_months": 3,
      "moratorium_variants": [],              # Term Loan: [{cond:"plantation_or_construction", months:12}]
      "moratorium_treatment": "SIMPLE_INTEREST",
      "women_rebate_pct": None,               # ELS only: 0.5
      "security_requirements": None,          # TO VERIFY — not published
  },

  "routing": {
      "eligible_partner_types": ["COOPERATIVE_BANK", "COOPERATIVE_SOCIETY", "SMALL_FINANCE_BANK"],
      "channel_capability": "PRESENCE_MANDATORY",   # conservative default, see 5.2
      "priority_allocation": None,            # TL & MFS: {"women": 0.40}
      "direct_application_permitted": False,  # true for every NSFDC scheme
  },

  "activities": {
      "taxonomy_ref": "NSFDC_INDICATIVE_ACTIVITIES_V1",   # §3.3
      "sectors_allowed": ["AGRI_ALLIED", "SMALL_INDUSTRY", "SERVICE_TRANSPORT"],
      "open_ended_clause": True,              # "any other legal and viable activity"
  },

  # ---- PLANE B: narrative, retrievable --------------------------------
  # myScheme section taxonomy. Each block is chunked + embedded for retrieval.
  "content": {
      "details":            [ContentBlock],   # purpose, objective, who it's for
      "benefits":           [ContentBlock],
      "eligibility_text":   [ContentBlock],   # the prose behind Plane A's numbers
      "application_process":[ContentBlock],   # online (PM SURAJ) + offline (SCA)
      "documents_required": [DocumentSpec],   # semi-structured, see below
      "faqs":               [FAQPair],
      "exclusions":         [ContentBlock],
      "sources":            [Reference],
  },

  # ---- PLANE C: assets -------------------------------------------------
  "assets": [ {"kind": "APPLICATION_FORM", "url": "...", "sha256": "...", "cached_at": "..."} ],

  # ---- support ---------------------------------------------------------
  "support": {"helpline": "1800110396", "portal": "https://pmsuraj.dosje.gov.in/"},
}
```

Two sub-types that earn their own shape:

```python
ContentBlock = {
  "block_id", "section", "text_en", "text_translated": {lang: str},
  "provenance": {...},
  "embedding": vector,          # for retrieval
  "is_quotable": bool,          # verbatim-safe for the user, vs. internal context only
}

DocumentSpec = {                 # semi-structured: drives the checklist AND the prose
  "doc_code": "CASTE_CERTIFICATE",
  "label": {"en": "...", "hi": "..."},
  "mandatory": True,
  "digilocker_available": True,        # drives the L2 pull (PRD-v3 §8)
  "digilocker_issuer_states": [...],   # TO VERIFY per state
  "accepted_alternatives": [...],
  "notes": ContentBlock,
}
```

`DocumentSpec` being semi-structured rather than prose is what makes **Zero-Rework Packet** and **One-Trip Promise** (`PRD-v3.md` §7.3) computable instead of advisory.

### 2.4 Retrieval and Q&A guardrails

Plane B is a small, closed, high-authority corpus — a few hundred blocks, not a web crawl. So:

- **Retrieve, then answer, always with a citation.** Every answer names its scheme and section. No retrieved block → *"I don't have that; here's the helpline"* — never a guess.
- **Never answer eligibility from Plane B.** Any question resolving to an eligibility decision routes to Plane A. If the user asks *"do I qualify?"*, the answer comes from the rules engine, and Plane B only supplies the surrounding explanation.
- **Cache by `(question_intent × scheme × language)`.** Most questions are the same few dozen; near-zero marginal LLM cost, consistent with v2's caching discipline.
- **FAQ pairs are pre-answered.** An FAQ match short-circuits generation entirely — retrieval returns the official answer verbatim, which is both cheaper and more accurate than paraphrasing it.
- **Translate once, at ingest, not per query.** Store `text_translated` per language in the corpus rather than translating at request time.

---

## 3. NSFDC corpus — Plane A values

`OFFICIAL` — `nsfdc.nic.in/scheme` + `/eligibility-requirements` + `/faqs`, fetched **2026-09-03**.

> **Confirm by eye before the finale.** One person, twenty minutes, on the live pages. These were retrieved through automated fetches; this project's standard is that a human reads the official page before a number is locked.

### 3.1 The five schemes

| Scheme | Project ceiling | Max loan | Interm. rate | **Beneficiary rate** | Tenure | Repayment | Moratorium |
|---|---|---|---|---|---|---|---|
| **Micro Finance (MFS)** | ≤ ₹1.40 L | ₹1.25 L | 2.5% | **6.5%** | 3 yr | **Quarterly** | 3 mo |
| **Term Loan** | ₹1.40–50 L | ₹45 L | 4% | **8%** | 7 yr | **Quarterly** | 6 mo (**12** plantation/construction) |
| **Aajeevika Micro-Finance** | ≤ ₹1.40 L | ₹1.25 L | 5% (NBFC-MFI) | **15%** | 3 yr | **Quarterly** | 3 mo |
| **Udyam Nidhi (UNY)** | ≤ ₹5 L | ₹4.50 L | 5% | **13% or 15%** — by partner type | 5 yr | Quarterly / half-yearly | 3 mo |
| **Educational Loan (ELS)** | ₹40 L or 90% of fee | ₹40 L | 2.5% | **6.5%** (−0.5% women) | 10–12 yr | — | course + 1 yr (or 6 mo) |

**Repayment is QUARTERLY, not monthly.** The PS asks for "EMIs" and v2's calculator computes a monthly instalment — but NSFDC's actual instalment is quarterly. Present **both**: the real quarterly instalment (what they'll actually be asked to pay) and a monthly equivalent (what they should budget). Getting this right is a small correctness win that a judge who knows the sector will notice, and getting it wrong makes every number in the demo subtly false.

**Dual rates are published for every scheme.** NSFDC lends to the channel partner at the intermediary rate; the partner lends on at the beneficiary rate. The spread is the partner's margin. Beneficiaries only ever pay the beneficiary rate — that is what the calculator uses — but holding both makes the channel-finance model explainable, which is a Problem Understanding point.

### 3.2 The rate depends on which partner you walk into

Udyam Nidhi is **13% via a Cooperative Bank or Society, 15% via a Small Finance Bank.** Same scheme, same borrower, different price — determined purely by which partner processes it.

This makes the router a **price optimiser**, not just a distance-and-eligibility filter, and produces a feature no competing team will have:

> *"The Small Finance Bank is 4 km away at 15%. The Cooperative Bank is 11 km away at 13%. Over your ₹4.5 L loan, the extra 7 km saves you ₹—."*

Fold this into `w1`–`w5` in `PRD-v3.md` §5.4 as a cost term, and surface it as a literacy feature (§7.2) — it is exactly "financial literacy regarding concessional lending," made concrete and personal.

### 3.3 The activity taxonomy — 148 official activities

`OFFICIAL` — `/indicative-activities`.

| Sector | Count | Examples |
|---|---|---|
| Agricultural & Allied | 20 | land purchase, goats/sheep/cattle, fisheries, horticulture, sericulture, tractors, power tillers |
| Small Industries | 51 | handlooms, hosiery, garments, flour mills, bakeries, handicrafts, leather goods |
| Service & Transport | 77 | retail shops, diagnostic centres, dental clinics, auto-rickshaws, commercial vehicles, hospitality |

Plus: *"any other legal and viable income-generating business activity... may be considered."*

**This replaces invented project categories in Tier 2.** Free text maps to NSFDC's *own* official list rather than to categories we made up — more accurate, and officially defensible: *"we classify against NSFDC's published indicative activities."* The open-ended clause means an unmatched activity is never a dead end; it becomes "may be considered — here's who to ask."

### 3.4 Other Plane A facts

`OFFICIAL` — from `/faqs` and `/eligibility-requirements`:

- **102 channel partners** — confirms the PS's "over 100"
- **Women: 40% fund allocation target** under Term Loan and Micro Finance. A woman applicant is in a priority category; say so, and weight routing accordingly
- **Skill development: free, NSQF-compliant, ₹1,500/month stipend, and NO income ceiling.** This makes **Train-then-Credit** (`PRD-v3.md` §7.1) much stronger — it isn't a consolation prize, it's free training that *pays* while you do it, open even to those above the loan income ceiling
- **Applicant types**: individuals, **partnership firms, cooperative societies** — v2 modelled individuals only. All members must be SC and each under ₹5 L
- **Direct application is prohibited** — "direct contact or correspondence by applicants/beneficiaries is not entertained." Confirms the PS and constrains L5 (`PRD-v3.md` §1.4)
- **Two application routes**: online via PM SURAJ, or offline via an SCA/authorised partner
- **Helpline 1800110396**; HQ at SCOPE Minar, Delhi; liaison centres in Mumbai, Kolkata, Lucknow, Bengaluru

---

## 4. Resolved conflicts

Two things `rules.md` recorded as unresolvable are now closed. Both are pitch assets.

### 4.1 The rate range — a wrong model, not a source conflict

`rules.md` spent five research passes on "irreconcilable" rates and concluded the question "hasn't converged and won't." **It had converged; the model had the wrong number of schemes in it.**

The PS says *"6.5% to 15% **depending on the scheme**"* and *"3 to 12 months"*. Three schemes cannot produce 15% or a 12-month moratorium. Five can, exactly: **15%** from Aajeevika and UNY (neither in the v2 model), **12 months** from Term Loan's plantation/construction variant, **6.5%** from MFS and ELS. The phrase "depending on the scheme" says outright that the range spans a portfolio. The PS text confirms the five-scheme reading **twice** — once on rates, once on moratorium.

### 4.2 The income ceiling — resolved, with a date

`rules.md` flagged ₹5 L (PS) against ₹3 L rural / ₹3.5 L urban (third-party) as unresolved.

`/eligibility-requirements` states it plainly: **annual family income must not exceed ₹5.00 lakh, rural and urban, effective 7 January 2026.**

The ₹3 L / ₹3.5 L figures are **stale** — the previous limits, before NSFDC raised and unified them. Every third-party source citing them simply hasn't updated. `OFFICIAL` and `PS-STATED` agree; there was never a live conflict, only an out-of-date internet.

This is worth saying out loud, because it is the PS's own thesis in miniature: *the information is fragmented and most of what's published about these schemes is out of date — which is exactly why a maintained, provenance-stamped corpus is the product.*

### 4.3 Age — v2 was right

v2 removed age fields as unverified. `/eligibility-requirements` states no age condition. **Keep them out.** Confirmed, not merely assumed.

---

## 5. Prudential norms and partner data

### 5.1 The rules

`OFFICIAL` — corroborated across sources; retained from `rules.md`, which got this right.

```python
PRUDENTIAL_NORMS = {
    "SCA": "cumulative_utilisation >= 1.0 AND has_active_overdues == False",
    "RRB": "net_npa < 15.0% in >=3 of preceding 6 FYs AND net profit in >=3 of those 6",
}
```

**The upgrade: this data is published.** `/performance-data` publishes nine datasets as Excel and PDF, including **state-wise cumulative funds utilisation** current to **2026-07-31**, state-wise and year-wise disbursement against notional allocation, and **channel-partner-wise** breakdowns. Since there is one SCA per state, state-wise cumulative utilisation *is* SCA-level utilisation — precisely what the SCA norm requires.

Tier 3 therefore upgrades from *real rule, mocked data* to **real rule, real published data, refreshed monthly.**

**What remains genuinely unavailable:**

| Field | Status | Position |
|---|---|---|
| SCA cumulative utilisation | **`OFFICIAL`, state-level, monthly** | Real |
| Channel-partner disbursement | **`OFFICIAL`** | Real |
| Branch-level utilisation | `MOCKED` | No public source; central monitoring is periodic |
| RRB net NPA, 6-year series | `MOCKED` | In individual RRB annual reports, not as a dataset. `TO VERIFY` whether NABARD consolidates |
| Active overdues to NSFDC | `MOCKED` | Internal to NSFDC |

**Disclose the mock in-product**, on every locator response — v2's `phrases.md` §6 already does this. Keep it. The negative finding is itself a result: no source — not NSFDC, not data.gov.in, not RBI — publishes a live branch-level NPA or utilisation API.

### 5.2 Channel partners

`OFFICIAL` — `/our-channel-partners`. **102 partners in 8 categories**, not the 4 the PS names:

SCAs · Public Sector Banks · Regional Rural Banks · NBFC-MFIs · **Cooperative Banks** · **Other Agencies & SIDBI** · **Small Finance Banks** · **Cooperative Societies**

The wider taxonomy matters twice: it's evidence of reading the primary source rather than the brief, and — per §3.2 — **partner category determines the beneficiary's interest rate**, so the categories are load-bearing, not descriptive.

**Ingestion**: PDF → table extraction (`pdfplumber` / `camelot`) → normalise → geocode via PIN dataset → `channel_partners`. Monthly, diffed against the previous version, changes logged — partner status changes are exactly what causes misrouting.

`channel_capability` per (scheme × partner type × state) has **no published source**. Seed from PM SURAJ's documented flow; correct via the Ground-Truth Loop. **Default every entry to `PRESENCE_MANDATORY`** — the conservative default never over-promises a service we can't deliver (`PRD-v3.md` §9.1).

Real SCAs for seeding (institution names `OFFICIAL`; any utilisation/NPA figures attached are `MOCKED` and must be labelled):

| State | SCA |
|---|---|
| Maharashtra | Mahatma Phule Backward Class Development Corporation (MPBCDC) |
| Tamil Nadu | Tamil Nadu Adi Dravidar Housing and Development Corporation (TAHDCO) |
| West Bengal | West Bengal SC ST Development and Finance Corporation |
| Andhra Pradesh | Andhra Pradesh Scheduled Castes Co-operative Finance Corporation |
| Delhi | Delhi SC/ST/OBC/Minorities & Handicapped Finance & Development Corporation (DSFDC) |

---

## 6. Verification sources

Full ladder in `PRD-v3.md` §8.

| Rung | Source | Gives | Licence | Confidence |
|---|---|---|---|---|
| L1 | **Aadhaar Paperless Offline e-KYC** | name, DOB, gender, address — UIDAI-signed | **none** — OVSE, not AUA | `OFFICIAL` |
| L2 | **DigiLocker Requester API** | **caste + income certificate, legally verified under the IT Act** | Requester onboarding: registered entity, domain email, DSC | `OFFICIAL` |
| L3 | Aadhaar authentication | full eKYC | AAGG Amendment Rules 2025 → sponsoring ministry → MeitY | `OFFICIAL` — notified 31 Jan 2025 |
| — | Account Aggregator | bank-statement income | **FIU status requires RBI/SEBI/IRDAI/PFRDA regulation** | `OFFICIAL` — closed to us directly; go via partner as TSP |

**Coverage caveat:** caste and income certificates on DigiLocker depend on each state's e-District integration. Coverage is real but uneven, and some listed issuers error in practice. Design for partial coverage — the ladder degrades to `DECLARED`, never blocks.

`TO VERIFY` — which states currently serve caste and income certificates via DigiLocker. Populates `DocumentSpec.digilocker_issuer_states` and drives Phase 2 district selection (`BUSINESS-PLAN.md` §6).
`TO VERIFY` — DigiLocker Requester per-pull pricing, for `BUSINESS-PLAN.md` §7.

---

## 7. The scraper

### 7.1 Don't write twenty scrapers

The instinct is one script per site. That produces twenty brittle files nobody maintains. Instead: **a declarative source registry plus five extractor strategies.** Adding a source becomes a config entry, not code — the same config-over-hardcoding discipline `rules.md` applied to numbers, applied to sources.

```yaml
# sources/nsfdc.yaml
- id: nsfdc_schemes
  url: https://nsfdc.nic.in/scheme
  strategy: HTML_TABLE
  cadence: monthly
  plane: A
  extract:
    scheme_rows: "table.scheme-list tr"
  map_to: Scheme.finance
  validate: [rates_between(0,30), ceilings_ascending, all_fields_present]

- id: nsfdc_utilisation
  url: https://nsfdc.nic.in/performance-data
  strategy: FILE_DOWNLOAD
  file_match: "*cumulative*utilisation*.xlsx"
  cadence: monthly
  plane: A
  map_to: PartnerPerformance

- id: nsfdc_faqs
  url: https://nsfdc.nic.in/faqs
  strategy: HTML_PROSE
  cadence: quarterly
  plane: B
  section: faqs
```

### 7.2 Five strategies cover every source

| Strategy | For | Tooling | Sources |
|---|---|---|---|
| `HTML_TABLE` | static tables | `httpx` + `selectolax` | NSFDC scheme/eligibility pages |
| `HTML_PROSE` | narrative → Plane B blocks | `httpx` + `selectolax` + chunker | FAQs, how-to-apply, indicative activities |
| `FILE_DOWNLOAD` | published Excel/PDF | `pandas`/`openpyxl`, `pdfplumber`/`camelot` | performance data, partner directory PDFs |
| `JSON_API` | SPAs with a discoverable backend | `httpx` | myScheme, API Setu, DigiLocker issuer list |
| `LLM_ASSISTED` | heterogeneous pages | LLM → strict Pydantic → validator | 20+ state SCA sites |

**Prefer published files over HTML wherever both exist.** NSFDC's Excel and PDF files are stabler than their page markup and are the format the publisher intended for reuse — a site redesign breaks a CSS selector but not a spreadsheet.

**For client-rendered pages, find the JSON API before reaching for a browser.** myScheme, the API Setu directory and the DigiLocker issuer list all returned navigation shells to a plain fetch — they're SPAs calling a backend. Open the network tab, find the endpoint, call it directly. `Playwright` is the fallback, not the default: it's an order of magnitude slower and far more fragile.

### 7.3 LLM-assisted extraction, with the guardrail that makes it safe

State SCA sites are the highest-moat data and the least uniform — every state's corporation has its own layout. Hand-writing 20+ parsers is unrealistic; an LLM extracting into a strict schema is exactly right here.

The guardrail is the same wall as §2.2:

```
LLM extraction  ->  Pydantic type/range validation  ->  cross-check vs known bounds
                                                          |
                    Plane B (narrative)  -->  auto-promote
                    Plane A (numbers)    -->  QUARANTINE, human review required
```

**The LLM's output is a proposal, never a promotion.** A model must never silently introduce an interest rate. Plane B rewording carries almost no blast radius and flows through; a changed Plane A number blocks until a person approves it. This is the "Plane A gates, Plane B flows" rule (§7.5 rule 4) enforced at the extraction boundary rather than trusted to discipline.

### 7.4 Pipeline

```
  scheduler (monthly, or on-demand)
        |
   [ fetcher ]     conditional GET (ETag / If-Modified-Since), retry w/ backoff
        |          -> unchanged? stop here. No parse, no diff, no version.
   [ parser ]      one of five strategies (7.2)
        |
   [ splitter ]    PLANE A (typed)  |  PLANE B (blocks)  |  PLANE C (assets)
        |                |                   |
   [ validator ]   schema+range      chunk, translate, embed
        |                |                   |
        +------- DIFF AGAINST PREVIOUS VERSION -------+
        |
        +--> Plane A changed?  -> QUARANTINE + alert a human
        +--> Plane B changed?  -> auto-promote
        |
   [ corpus vN+1 ]  immutable, provenance-stamped
        |
   L2/L3/L4 read a PINNED version, never "latest"
```

**Content-hash first.** Most monthly runs will find nothing changed; hashing before parsing makes the steady state nearly free and keeps our footprint on government servers minimal.

**Government sites are flaky — design for it.** NSKFDC refused connection outright on 2026-09-03. Per-source timeout, exponential backoff, and on total failure **serve the last good version with its age visible**. A beneficiary must never be blocked because a government site is down.

**Conduct.** All sources are public government pages. Monthly, not continuous · conditional GET so unchanged pages cost one HEAD · honest User-Agent identifying the project with a contact · respect `robots.txt` · single-threaded per host with a delay. This is defensible in front of a ministry, which matters more here than crawl speed.

### 7.5 Five rules, each earning its place:

1. **Never overwrite.** Every ingest produces a new immutable version. Recommendations record the version that produced them, so a September recommendation is still explainable in March.
2. **Diff and alert.** A rate that changes silently is a correctness bug. Surface every change for human review before promotion. §4.2 shows why this matters: the ₹5 L limit has an effective date, meaning these numbers demonstrably *do* change.
3. **Provenance on every field** — `source_url`, `fetched_at`, `confidence`. No number enters the corpus unattributed.
4. **Plane A changes gate; Plane B changes flow.** A changed interest rate blocks promotion until reviewed. A reworded FAQ promotes automatically. Different blast radius, different ceremony.
5. **Degrade, don't fail.** If a source is unreachable — as NSKFDC was on 2026-09-03 — serve the last good version with its age visible. Never block a beneficiary because a government site is down.

**Scraping conduct:** all sources are public government pages. Fetch monthly, not continuously; identify honestly; respect `robots.txt`; cache aggressively. Prefer the published Excel and PDF files over HTML scraping where both exist — they're stabler and they're the format the publisher intended for reuse.

---

## 8. Ground-truth corrections

The only dataset here that is ours, and the only one a competitor cannot obtain (`PRD-v3.md` §7.3, `BUSINESS-PLAN.md` §5).

| Field | Corrects |
|---|---|
| Branch address accuracy | source #8 / #22 geocoding |
| Does this branch process this scheme | `channel_capability`, `eligible_partner_types` |
| **Actual rate quoted at the counter** | `beneficiary_rate_by_partner_type` — §3.2 is published, but only ground truth confirms it's honoured |
| Documents demanded but not on our checklist | `DocumentSpec` — the hidden-document problem behind repeat trips |
| Days from submission to disbursement | SLA and Speed Flywheel signal, **without partner integration** |

**Safeguards:** N corroborating reports before any rating moves · aggregate-only, never attributable · integrity complaints to the formal grievance channel, never published · social incentive, never cash.

---

## 9. Next actions

1. **Confirm §3 by eye** on the live NSFDC pages. Twenty minutes, before internals.
2. **Fetch the four un-fetched NSFDC pages** — `/how-to-apply-2`, `/form`, `/allocation-of-funds`, `/annual-reports`. These populate Plane B's `application_process` and Plane C's forms, and they're the last big content gap.
3. **Extract the 148 activities in full** from `/indicative-activities` into `NSFDC_INDICATIVE_ACTIVITIES_V1`. This is the Tier 2 taxonomy — high value, one page.
4. **Download the nine performance-data files**; build the state-wise utilisation table. The single highest-value half-day in the project.
5. **Download the eight partner-category PDFs**; build the extraction pipeline.
6. **Retry NSKFDC** (source #15).
7. **Enumerate DigiLocker caste/income issuer coverage** by state → Phase 2 district choice.
8. **Resolve the myScheme API endpoints** on API Setu (source #18).
9. **Update `architecture.md` and `rules.md`** to point here for scheme numbers and eligibility, and to reflect `PRD-v3.md` §5.
