# Business Plan — Yojna Setu

**The origination layer for India's social-justice credit channel.**
Companion to `PRD-v3.md`. Sources and confidence levels in `data-sources.md`.

> **A note on numbers.** This project has twice been burned by confident-sounding fabricated statistics. Every figure below is marked `[VERIFIED]` with its source, or `[TO VERIFY]` with the method for obtaining it. **Do not quote a `[TO VERIFY]` number to a judge or an investor as fact.** A sizing method with honest gaps beats a precise-sounding invention, and saying so is itself a credibility asset.

---

## 1. The thesis in one paragraph

India runs six national finance and development corporations that lend concessionally to marginalised communities through a "channel finance" model — money flows to State Channelizing Agencies, banks and NBFC-MFIs, who lend onward. The model exists because direct lending at this scale is impractical. But it creates a fragmentation problem the government has never solved on the demand side: a beneficiary cannot tell which scheme fits, cannot find a partner authorised to process it, and cannot tell whether that partner is currently able to disburse at all. India's flagship credit portal, JanSamarth, does not cover any of these corporations. **The entire social-justice credit channel has no digital front door.** Yojna Setu is that front door — and, because it verifies rather than merely recommends, it produces something a lender can act on instead of advice a lender must re-do.

---

## 2. Market

### 2.1 The six corporations

| Corporation | Target group | Ministry |
|---|---|---|
| **NSFDC** | Scheduled Castes | Social Justice & Empowerment |
| **NSKFDC** | Safai Karamcharis & manual scavengers | Social Justice & Empowerment |
| **NBCFDC** | Backward Classes / OBC | Social Justice & Empowerment |
| **NHFDC** | Persons with disabilities | Social Justice & Empowerment (DEPwD) |
| **NSTFDC** | Scheduled Tribes | Tribal Affairs |
| **NMDFC** | Minorities | Minority Affairs |

`[VERIFIED]` — all six exist and operate the same SCA-based channel-finance structure. **One engine serves all six.** The eligibility rules differ; the architecture does not. This is what makes the product a platform rather than a project.

`[VERIFIED]` PM SURAJ (`pmsuraj.dosje.gov.in`) already unifies applications for NSFDC + NSKFDC + NBCFDC — confirming the government itself treats these as one addressable channel, and giving us a rail to integrate with rather than displace.

### 2.2 Sizing method

Don't guess a TAM. Compute it from published data, which exists:

```
Addressable beneficiaries  = eligible population per corporation
                             x  share below the income ceiling
Annual channel throughput  = sum of annual disbursement across the six corporations   [from published performance data]
Serviceable volume         = annual applications routed through channel partners
Revenue-bearing volume     = applications where we assist + verify
```

`[VERIFIED]` NSFDC publishes year-wise disbursement, beneficiary counts, state-wise cumulative utilisation and channel-partner-wise breakdowns as Excel — current to 2026-07-31. NBCFDC publishes annual reports and a dashboard. **Inputs 2 and 3 are directly obtainable.** `[TO VERIFY]` — pull them and populate this section before any external pitch; it is a half-day of work and converts this whole section from method to fact.

`[TO VERIFY]` The most quotable single number will be **annual disbursement across all six corporations**. Obtain from each corporation's annual report. Do not estimate it.

### 2.3 The gap, stated precisely

`[VERIFIED]` JanSamarth — the Department of Financial Services' national credit portal — carries **15 schemes** and **269 partner banks**, with Aadhaar/PAN/GSTIN integration and digital approvals. Its 15 schemes are: CGSE, Home Loan for EWS/LIG/MIG, Loan for Startups, e-Kisan Upaj Nidhi, Kisan Credit Card, KCC-Fisheries, Rooftop Solar, ACABC, Agriculture Infrastructure Fund, PMEGP, Weaver Mudra, PMMY, PM SVANidhi, NAMASTE, and DAY-NULM.

**Zero NFDC products.** Not an oversight — a structural consequence. JanSamarth is built for direct bank lending; the NFDCs lend through SCAs. The plumbing doesn't match, so the channel was left out.

That is the wedge: **the one large government credit channel that India's flagship credit portal structurally cannot serve.**

---

## 3. Product-market fit: who has the pain

| Actor | Pain today | What we give them | Will they pay? |
|---|---|---|---|
| **Beneficiary** | Doesn't know schemes exist; 3–4 wasted trips; middleman extraction | Right scheme, proven eligibility, one successful trip | **Rarely, and never as a gate** |
| **CSC / VLE operator** | Wants more billable e-governance services | A new service line with a commission | No — they earn |
| **Channel partner (SCA/bank/MFI)** | Incomplete, misrouted paper; can't hit disbursement targets | Pre-verified packets, triaged queue | **Yes** — per application |
| **Corporation (NSFDC etc.)** | Poor last-mile visibility; funds idle at year end | Coverage-gap and utilisation intelligence | **Yes** — B2G licence |
| **CSR sponsor** | CSR spend with unmeasurable impact | Auditable per-application impact | **Yes** — sponsorship |

The beneficiary has the most pain and the least ability to pay. **That asymmetry defines the model**: monetise the three actors with budgets, keep the beneficiary free.

---

## 4. Business model

### 4.1 Free forever, no exceptions

Eligibility · EMI and True Cost · every financial-literacy feature · partner locator and maps · document checklist · the One-Trip Promise pack.

This is a constraint, not a growth tactic. A platform serving SC beneficiaries under ₹5 L family income that paywalls its core would deserve the criticism it received.

### 4.2 Four revenue lines

**(a) Assisted-submission convenience fee.** The only beneficiary-facing charge, and only where `channel_capability != PRESENCE_MANDATORY` (`PRD-v3.md` §9.1) — we never sell what we can't deliver.

`[VERIFIED]` Precedent: CSCs charge government-notified service fees for e-governance services. The free path stays open and visible (`PRD-v3.md` §10.2).

**Payer waterfall — the beneficiary is the last payer, not the first:**
1. CSR sponsor
2. Partner lender origination fee
3. SCA / corporation B2G contract
4. Beneficiary — last resort, capped, waivable

In a well-run district, the beneficiary-paid share should trend toward **zero** as CSR and partner coverage grows. That's the target, and it's measurable.

**(b) Partner origination fee.** Per accepted, pre-verified application. The partner is acquiring a borrower with verified caste and income, a complete document set and a drafted project report — work they would otherwise do themselves at higher cost and lower success. Standard, legal, and precedented in the DSA/business-correspondent model.

**(c) B2G SaaS.** Per-state licence to SCAs and corporations for the partner console, coverage-gap maps, utilisation intelligence and absorption alerts. Public bodies with allocated budgets buying operational software is a well-worn procurement path.

**(d) CSC/VLE commission share.** Revenue share on assisted submissions completed by operators. Aligns the distribution channel with volume.

### 4.3 CSR — the channel that makes the beneficiary fee disappear

`[VERIFIED]` **Companies Act 2013, Section 135(1)**: applies to any company with net worth ≥ **₹500 crore**, *or* turnover ≥ **₹1,000 crore**, *or* net profit ≥ **₹5 crore**. Obligation: at least **2% of average net profits of the three immediately preceding financial years**.

`[VERIFIED]` **Schedule VII** expressly includes *"measures for reducing inequalities faced by socially and economically backward groups"*, and separately covers socio-economic development and welfare of **Scheduled Castes**, STs, OBCs, minorities and women.

So sponsoring scheme access for SC beneficiaries is squarely eligible spend. No stretching.

**The actual sell is not the cause — it's the measurability.** Most CSR spend reports activity, not outcome, and CSR reporting increasingly demands impact numbers. Yojna Setu emits a per-application audit trail: *N applications filed, ₹Y credit unlocked, Z disbursed, in these districts, for these beneficiaries.* That auditability is the product a CSR head is buying.

**Sharpest first call: banks and NBFCs.** They carry CSR obligations *and* priority-sector lending targets. Sponsoring Yojna Setu in a district earns Schedule VII credit **and** produces a pipeline of PSL-eligible, pre-verified borrowers — from the same rupee. That double-count is rare, and it makes the first BD conversation unusually easy.

---

## 5. Moats

Ordered by how hard each is to copy.

**1. Regulatory doors.** Each takes months and an institutional relationship, not engineering:
- **Aadhaar authentication** under the AAGG (Social Welfare, Innovation, Knowledge) Amendment Rules 2025 `[VERIFIED — notified 31 Jan 2025]`, whose listed purposes include verbatim *"prevention of dissipation of social welfare benefits."* Approval routes through the sponsoring ministry → MeitY. **The sponsoring ministry here is MoSJE — the author of this problem statement.** Winning this PS is the introduction.
- **DigiLocker Requester** status for legally-verified caste and income certificates.
- **TSP to FIU** for Account Aggregator income flows.

First party through these doors holds a lead measured in quarters.

**2. The data corpus, which compounds monthly.** Nobody has compiled: six corporations × schemes × state SCA variations × the official partner directory × monthly utilisation time series × `channel_capability` per state. Every month of operation deepens it, and the historical utilisation series cannot be back-filled by a competitor starting later.

**3. Ground truth.** Every beneficiary visit returns corrections — is the branch there, does it process this scheme, what did they ask for that wasn't on the list, how long did it take. This is **unpurchasable** operational reality about how the channel actually behaves, and it improves routing in a loop competitors can't shortcut. It also removes our dependence on partner cooperation for disbursement-timing data.

**4. Two-sided network.** Beneficiaries attract partners; partner participation improves routing quality; better routing attracts beneficiaries. Standard, and real here because both sides currently have nothing.

**5. Workflow lock-in.** Once an SCA runs its intake queue on the console, switching costs are institutional — retraining, process change, historical records. Public-sector switching costs are especially high.

**6. Trust.** In welfare, being the ministry-recognised channel is a durable position, and the free-forever core plus Fraud Shield is what earns it with beneficiaries.

---

## 6. Go-to-market

Deliberately sequenced. Each phase unlocks the next; skipping ahead fails.

**Phase 1 — Win the PS (now → SIH finale).**
Deliverable is credibility and the MoSJE relationship, not revenue. A working demo, honest about what's mocked, that visibly solves the ministry's stated problem.

**Phase 2 — One district, end to end (0–6 months post-SIH).**
Pick a single district in a state with a cooperative SCA and reasonable DigiLocker coverage. Sign one SCA, one NBFC-MFI, and 10–20 CSC operators. Target: **first-time-right rate and trips-per-application**, not user count. The proof point that sells everything after is *"applications through Yojna Setu are accepted first time at X%, versus Y% baseline."*

**Phase 3 — One state (6–18 months).**
Scale to the state SCA. Land the first B2G console licence and the first CSR sponsorship. Begin the DigiLocker Requester and AAGG approval processes — start early, they're slow.

**Phase 4 — Multi-corporation (18–36 months).**
Same engine, new corpora: NBCFDC and NSKFDC first (PM SURAJ already unifies these three, so the government has pre-validated the grouping), then NSTFDC, NMDFC, NHFDC.

**Phase 5 — The horizontal (36 months+).**
The engine — verified eligibility, routing, packet origination — is not specific to credit. State welfare departments, scholarships, pensions, housing all have the same shape. `[VERIFIED]` myScheme lists 4,700+ central and state schemes with the same discovery problem. That is the long-run company.

### 6.1 Distribution — the honest problem

**The PS's root cause is awareness, and awareness is a distribution problem no chatbot solves.** A beneficiary who doesn't know NSFDC schemes exist also doesn't know Yojna Setu exists. Any plan that assumes inbound WhatsApp traffic is fooling itself.

Three channels that actually reach this demographic, in priority order:

1. **CSC / VLE operators** — already trusted, already transactional, already the last mile for e-governance. `[TO VERIFY: current national CSC count]`
2. **The SCAs themselves** — they have field staff, outreach mandates and disbursement targets they're missing. We make them look good; they bring the beneficiaries.
3. **SHGs and NGOs** — organised groups of exactly this demographic, reachable in bulk.

Beneficiary self-discovery via WhatsApp is a *fourth* channel, not the first. This is precisely why assisted mode is load-bearing rather than optional (`PRD-v3.md` §6.3).

---

## 7. Unit economics

Structure now; fill from Phase 2 pilot data. **Do not present invented figures.**

```
Revenue per assisted application
    = convenience fee (or CSR/partner-funded equivalent)
    + partner origination fee
    - CSC commission share

Cost per assisted application
    = LLM inference (project report + explanation, heavily cached)   ~ near-zero at current free tiers
    + verification API cost (DigiLocker per-pull)                    [TO VERIFY: Requester pricing]
    + WhatsApp conversation cost                                     ~ zero within the 24h service window
    + support / exception handling                                   <- the real cost driver
    + amortised corpus maintenance

B2G licence revenue is near-pure margin (same corpus, same console).
```

Two observations that shape the model:

- **Marginal technology cost is genuinely near zero.** Caching (v2's design already fingerprints on outcome, not raw input), deterministic templates for seven of eight literacy features, and free-tier inference mean the *software* barely costs anything per application.
- **The real variable cost is human exception handling** — a document that won't pull, a partner that rejects, a user stuck mid-flow. So the metric that actually governs unit economics is **first-time-right rate**, which is also the metric that governs beneficiary outcomes. Those being the same number is a healthy property of this business.

---

## 8. Governance and ethics

Not a compliance appendix — this is a product for people with little power and less recourse, and getting it wrong is the failure mode that matters most.

**Never gate on payment.** Eligibility, literacy and locator are free permanently (§4.1).

**Never gate on verification.** A user in a state with no DigiLocker integration gets a full recommendation, labelled `DECLARED`. The ladder degrades; it never blocks (`PRD-v3.md` §8).

**Never claim approval.** We recommend, verify and route. The credit decision belongs to the channel partner, always, and every output says so.

**Never lend, never touch funds.** No custody, no credit decisions, no underwriting. This keeps us outside RBI lending regulation by design, not by accident.

**Data minimisation on the most sensitive fields there are.** Caste is high-sensitivity personal data under DPDP. We never store an Aadhaar number — L1 verification is designed so we never receive one. Prefer storing certificate *assertions* over document copies. Itemised consent, real deletion, easy withdrawal.

**Ground-truth data is aggregate-only**, corroboration-thresholded, never attributable to an individual reporter or published as an accusation against a named officer. Integrity complaints route to the formal grievance channel.

**No dark patterns on the paid path.** The free route is shown with equal prominence, in the same message, in the same size.

**A PPP structure is the natural end state.** The most defensible long-run position is not "startup extracting from welfare" but a ministry-recognised digital public infrastructure operator — closer to how NPCI or CSC e-Governance Services are structured. Worth saying out loud when a judge or an investor asks the uncomfortable question, because someone will.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| **Government builds it themselves** | Most likely outcome, and it isn't fatal — PM SURAJ exists and we integrate rather than compete. The defensible position is being the operator they adopt (moats 1–3), not the portal they replace |
| **SCA adoption is slow** | Public-sector sales cycles are long. Phase 2 targets one cooperative SCA, not many; CSC channel provides volume meanwhile |
| **DigiLocker coverage stays patchy** | Ladder degrades to `DECLARED` (`PRD-v3.md` §8); the L1 Aadhaar offline rung needs no state integration at all |
| **Fee optics** | Payer waterfall puts the beneficiary last; free path always visible; target beneficiary-paid share → 0 |
| **Scheme rules change** | Corpus is versioned and provenance-stamped; a rate change is a data edit |
| **Ground-truth gaming** | Corroboration thresholds, aggregate-only, social not cash incentive |
| **Regulatory creep into lending** | We never lend, decide credit, or hold funds (§8) |
| **Single-corporation concentration** | Multi-corporation architecture from day one; NSFDC is the first tenant, not the product |

---

## 10. What to do next week

1. **Pull the published performance data** from NSFDC and NBCFDC and populate §2.2. Half a day; converts the market section from method to fact.
2. **Confirm the scheme corpus by eye** against `nsfdc.nic.in/scheme` (`data-sources.md` §3) — one person, twenty minutes, before internals.
3. **Ask the MoSJE SPOC one question**: who at NSFDC owns channel-partner performance data, and would they share branch-level figures with a ministry-endorsed pilot? The answer determines whether Tier 3 ever goes fully live.
4. **Identify the Phase 2 district.** Cooperative SCA, decent DigiLocker coverage, reachable for field visits.
5. **Draft the CSR one-pager** aimed at bank and NBFC CSR heads, leading with the PSL + Schedule VII double-count (§4.3).
