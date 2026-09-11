# memory.md — Project status
Update this at the end of every session, whoever's driving (human or AI agent). Next session reads this first, before architecture.md.

---

## Last updated
2026-09-07, MVP build. Branch feat/mvp-corpus-routing. 195 tests passing.

## Current phase
**MVP items 1-9 and 13 COMPLETE**, WhatsApp flow wired to the new engine, web portal + landing live. Branch `feat/mvp-corpus-routing`, 195 tests. Not merged to main.

**Phase 3 — COMPLETE.** Gemini integration for LLM extraction and generation, coupled with robust SQLite caching based on deterministic outcome fingerprints. 72/72 tests passing.

## Done
- Problem statement selected and locked: SIH26092 (NSFDC scheme matching), extending the existing GrantBot codebase rather than starting fresh.
- Full architecture designed: three-tier pipeline (deterministic rules → light semantic matching for free text → prudential/geo routing), model strategy (Gemini primary, OpenRouter open-source fallback with ZDR privacy settings, IndicTrans2 translation bridge), reliability fix for the prior WhatsApp failure (async webhook + LangGraph checkpointer for state).
- Doc suite written: `prd.md`, `architecture.md`, `rules.md`, `phrases.md`, `prompt.md`, this file.
- Master Build Guide written: live-verified corrections to all planning docs, per-phase implementation specs.
- SIH 2026 judging rubric confirmed: 5 criteria × 20 marks, averaged across judges.
- MUJ SPOC contacted; meeting scheduled Monday. Team nomination quota (45+5) confirmed from prior experience, pending reconfirmation at that meeting.
- **Phase 0 — Webhook → Queue → Worker skeleton:**
  - `pyproject.toml` — project config with all Phase 0 deps
  - `.env.example` — secret template (LANGGRAPH_STRICT_MSGPACK removed — not a real env var)
  - `.gitignore` — updated with project-specific entries
  - `src/__init__.py`, `src/config.py`, `src/database.py`, `src/webhook.py`, `src/worker.py`, `src/graph.py`, `src/whatsapp.py`, `src/main.py` — all built and working
  - `tests/test_phase0.py` — 13 tests, all passing
  - Twilio HMAC-SHA1 verification (not SHA256 — corrected from architecture.md)
  - LangGraph AsyncSqliteSaver checkpointer for state persistence
  - GC-safe asyncio task management
  - Per-user rate limiting (in-memory token bucket)
- **Phase 1 — Tier 1 Rules Engine + EMI Calculator + Intake Flow:**
  - `src/config.py` — removed unverified age fields (min_age, max_age, requires_student, target_category). Added default_tenure_months (84) and default_moratorium_months (6) from NSFDC direct verification. Added explanatory comment about why age is deliberately absent.
  - `src/schemes.py` — UserProfile (Pydantic), SchemeMatch (dataclass), evaluate_eligible_schemes() — pure-function Tier 1 engine. Boundary-correct: income ≤ 500000 matches, 500001 doesn't.
  - `src/calculator.py` — EMI calculator with 3 moratorium treatments (simple interest, capitalized, subvention). Women's 0.5% rebate for Educational Loan. Fixed edge case: zero moratorium months now returns 0 payment.
  - `src/graph.py` — Rewritten with conversational intake flow (project_type → cost → income → gender → results). Kept `process_message()` for Phase 0 test backward compat. Fixed latent bug where `check_consent` didn't clear stale response for already-consented users.
  - `tests/test_schemes.py` — 26 boundary-value eligibility tests (income at exactly ₹5L, cost at ceilings, project type routing, category check, women's rebate)
  - `tests/test_calculator.py` — 23 tests (3 moratorium types, women's rebate, edge cases, financial invariants)
  - **Total: 62/62 tests passing.** Phase 0 did not regress.
- **Phase 2 — WhatsApp Flow for structured intake:**
  - `src/config.py` & `.env.example` — added `content_sid_project_type`, `content_sid_gender`, and `use_button_messages` toggle.
  - `src/whatsapp.py` — added `send_whatsapp_buttons()` using Twilio Content API with graceful fallback to plain text.
  - `src/graph.py` — modified state schema (`button_payload`, `response_content_sid`). Intake steps try `ButtonPayload` first, then text parser fallback.
  - `src/worker.py` — integrated button routing based on `response_content_sid`.
  - `tests/test_buttons.py` — 4 tests verifying `ButtonPayload` parsing, text fallback, and response routing.
  - **Total: 66/66 tests passing.** No regression in text-only Sandbox fallback.
- **Phase 3 — Gemini Integration & Caching:**
  - `pyproject.toml` — added `langchain-google-genai>=4.0.0`.
  - `src/cache.py` — SQLite LLM caching utilizing deterministic fingerprints (hashing scheme outcome fields rather than continuous inputs like exact income).
  - `src/llm.py` — configured Gemini Flash-Lite for Tier 2 extraction (protecting free tier limits) and Gemini Flash for outcome generation using structured outputs.
  - `src/graph.py` — integrated `await check_cache_for_outcome` and fallback to async LLM generation within `process_intake`. Transitioned state testing routines and nodes to fully async.
  - `tests/test_llm.py`, `tests/test_cache.py`, and updated test suites (`test_phase0.py`, `test_buttons.py`) for async concurrency.
  - **Total: 72/72 tests passing.** No regression.

## In progress
Nothing in code. Doc suite re-baselined on 2026-09-03 — see `PRD-v3.md` §12 for the revised build ladder.

## Next up (in order)
1. **Confirm the 5-scheme corpus by eye** on nsfdc.nic.in/scheme (`data-sources.md` §2.2) — 20 min, before internals.
2. **Download NSFDC performance-data files** and build the state-wise utilisation table (`data-sources.md` §8) — this is what makes Tier 3 real instead of mocked.
3. **Phase 4 — Tier 3 partner locator + prudential routing**, now on real published utilisation data.
4. Update `config.py` from 3 schemes to 5; add `education_status` and family-income intake fields.

## Left / not started
- Tier 3 (partner locator + prudential routing) with mocked utilization data.
- OpenRouter fallback chain + IndicTrans2 translation bridge.
- Multilingual button flow.
- Everything frontend/web-dashboard.

## Open / blocked on
- Exact NSFDC scheme numbers — genuinely unresolved. Waiting on SPOC meeting or direct SCA contact.
- MUJ's specific submission rules (AI-narration policy, exact format) — to confirm Monday.

## Session log
*(Newest first)*

- **2026-09-07 — graph wiring + Aadhaar verification.** 176 -> 195 tests.
  - **`graph.py` wired to the new engine.** WhatsApp now returns the same output as the portal. Fixed two bugs in the process: `_format_emi_details` priced EVERY scheme with the global `default_tenure_months` (84) and `default_moratorium_months` (6) instead of each scheme's own terms, and produced a MONTHLY instalment for what are quarterly loans. New `_price()` uses per-scheme tenure/moratorium/periods_per_year; new `_format_outcome()` composes the deterministic literacy blocks (instalment, true cost, moratorium strip, moneylender, scheme comparison, why-not, priority, fraud shield). LLM still writes the intro only — no rupee figure a borrower sees is generated.
  - **Item 13 — Aadhaar Paperless Offline e-KYC** (`src/verification.py`). Needs NO licence: the resident downloads their own UIDAI-signed XML and supplies the share code; verifying it makes us an OVSE, not an AUA. Full enveloped XMLDSig verification by hand with `cryptography` + `lxml` (no signxml dep): C14N the body minus the Signature, SHA-256, compare to DigestValue, then RSA-verify SignatureValue over canonicalised SignedInfo. BOTH checks matter — digest alone allows a forged signature, signature alone allows a swapped body. Tests build a real RSA-signed document and prove tampering with the name or address is caught, and that a different signer is rejected.
  - Grades VERIFIED/DECLARED and **never gates**: an unverified user gets the identical recommendation. Proves name/DOB/gender/address only — NOT caste or income, which need DigiLocker Requester onboarding (PRD-v3 §8 rung L2). Says so explicitly when UIDAI's cert isn't configured rather than claiming verification it didn't do.
  - `POST /api/verify` + `<av-verify>` custom element in the portal.
  - **NOT visually verified**: the redesign from the previous session and this verification control have never been seen in a browser. Chrome disconnected, then the dev server start was declined. Worth an eyeball before demoing.

- **2026-09-04 — MVP build (items 1-7, 9).** Branch `feat/mvp-corpus-routing`. 72 -> 161 tests.
  - **Corpus**: `corpus/v1/schemes.json` is now the single source of truth with per-field provenance; `config.SCHEMES` is a derived view; the dead `schemes` DDL table is deleted. Five schemes, not three.
  - **Fixed a live bug**: project types lived in a module-level dict and a scheme missing from it matched EVERY project type — Udyam Nidhi (business) was being offered to education applicants the moment the corpus grew. Now corpus-sourced, empty list = load-time error.
  - **Eligibility**: `EligibilityResult` with matches + rejections (stable `rule` tags) + No-Dead-Ends referral. `evaluate_eligible_schemes()` kept as a wrapper so cache/llm/graph are untouched.
  - **Calculator**: `periods_per_year` (default 12 so all 23 existing tests pass byte-identically); NSFDC repays QUARTERLY. Integer period math — float division would render "over 78.0 months" live.
  - **Literacy** (`src/literacy.py`, all deterministic, no LLM): True Cost, quarterly+monthly instalment, moratorium strip, Why/Why-Not, fraud shield, priority note, moneylender comparison, scheme comparison.
  - **Ingest** (`src/corpus/ingest.py`): real NSFDC data. Tier 3 is no longer mocked. 36 states x 9 FYs, current to 31 Jul 2026; for FY2025-26, 11/36 states meet the 100% SCA norm. Two parser bugs found against the real file (title row contains both header keywords; the sheet stacks several tables with different layouts). Self-consistency guard drops rows where published %AGE disagrees with actual/allocation.
  - **Routing** (`src/routing.py`): hard exclusions with user-facing reasons; separates fresh-release eligibility from deployable headroom; scores travel/cost/headroom; Cheapest Route silent where no spread is published; disclosure computed per response from row confidence.
  - **Pitch figures corrected**: the script's Rs 22,300 is not reproducible. Real: Rs 12,568 scheme interest vs Rs 1,78,200 moneylender on Rs 1.08L. And at Rs 1.2L a user matches MFS at 6.5% AND Aajeevika at 15% — Rs 29,389 apart on the same project, which is a stronger Cheapest-Route beat than the partner-type one and needs no story change.
  - **Environment note**: no venv; running on miniconda base. langgraph, aiosqlite, langchain-google-genai, selectolax were missing and were installed.
  - **Maps** (`src/maps.py`): hand-rolled OSM tile compositor (httpx + Pillow) rather than `staticmap` — OSM's tile policy needs an identifying User-Agent, and the local tile cache makes the map render offline after one warm run. Served on ONE narrow `/media/{token}.png` route, not a StaticFiles mount: the URL is public and encodes an approximate location (DPDP).
  - **Outstanding**: item 10 (script detection + Hindi copy), 11 (voice — highest technical risk), 12 (console, decided as a separate Next.js app), 13 (Aadhaar offline XML verify), 14 (demo ops / cache warming). Also: nothing is wired into `graph.py` yet — the engine is built and tested but the WhatsApp conversation still runs the old 3-scheme flow. That is the next task.

- **2026-09-03 — PRD v3 + business plan.** No code. Re-scoped the project from "PS deliverable checklist" to an origination layer. Wrote `PRD-v3.md`, `BUSINESS-PLAN.md`, `data-sources.md`. Key findings: (1) **the scheme numbers had converged all along** — NSFDC runs 5 schemes, not 3, and the PS's own "6.5-15% depending on the scheme" and "3-12 month" ranges only reconcile with all five, so `rules.md`'s five-pass deadlock was a wrong-model problem, not a source-conflict problem; (2) **NSFDC publishes state-wise cumulative funds utilisation as Excel** (to 2026-07-31), so Tier 3 upgrades from mocked to real data; (3) **JanSamarth covers 15 schemes / 269 banks and zero NFDC products** — that is the market gap; (4) **Aadhaar Paperless Offline e-KYC needs no AUA licence**, giving real identity verification inside a hackathon build; (5) AAGG Amendment Rules 2025 permit private Aadhaar auth for "prevention of dissipation of social welfare benefits", sponsored by the ministry — which here is MoSJE, the PS author. Added financial-literacy, faster-disbursement and fund-utilisation feature sets against the PS's two impact goals, which v2 had no features for.
  **Second pass — corpus schema redesign.** The 11-numeric-field scheme schema was too thin; NSFDC's pages carry far more. Redesigned as a **two-plane corpus**: Plane A (typed, deterministic, feeds Tier 1 — never LLM-touched) vs Plane B (narrative: purpose, benefits, process, documents, FAQs — retrievable for Q&A, never decides eligibility), mirroring myScheme's national section taxonomy. New findings from the sub-pages:
  - `/eligibility-requirements` — **income ceiling is Rs 5L, rural AND urban, effective 2026-01-07.** This resolves `rules.md`'s Rs 3L/Rs 3.5L conflict outright: those are the OLD limits and every third-party source citing them is stale. Also confirms **no age criterion** (v2's removal of age fields was right) and that **partnership firms + cooperative societies** are eligible, not just individuals.
  - `/scheme` — **repayment is QUARTERLY, not monthly** (calculator correctness bug in the current build). **Dual rates published** (intermediary vs beneficiary). **Udyam Nidhi's beneficiary rate depends on partner type** — 13% via Cooperative Bank/Society, 15% via Small Finance Bank. Makes the router a price optimiser, not just a distance filter.
  - `/indicative-activities` — **148 official fundable activities in 3 sectors** (20 agri, 51 small industry, 77 service/transport). This is the Tier 2 classification taxonomy; stop inventing project categories.
  - `/faqs` — **102 channel partners**; **women have a 40% fund-allocation target** under TL and MFS; **skill training is free, NSQF-compliant, pays Rs 1,500/month stipend and has NO income ceiling** (makes Train-then-Credit strong, not a consolation prize); helpline 1800110396.
  - Still un-fetched: `/how-to-apply-2`, `/form`, `/allocation-of-funds`, `/annual-reports`. Security/collateral requirements are published nowhere found.
  `rules.md` is superseded on scheme numbers AND eligibility by `data-sources.md` §3-§4.
  **Third pass — scraper, language, voice, MVP.** Scraper designed as a *declarative source registry + 5 extractor strategies* (HTML_TABLE / HTML_PROSE / FILE_DOWNLOAD / JSON_API / LLM_ASSISTED), not 20 bespoke scripts — adding a source is a config entry. LLM-assisted extraction is allowed for heterogeneous state SCA sites but its output is a *proposal*: Plane B auto-promotes, Plane A quarantines for human review. Prefer published Excel/PDF over HTML; for SPAs (myScheme, API Setu, DigiLocker issuer list) find the JSON API before reaching for Playwright. Language: **guess-then-confirm-in-one-tap**, not auto-detect and not always-ask — cascade is PIN->state->language (strongest, and we collect PIN anyway) > location share > **Unicode script detection** (free, deterministic, immediate) > explicit buttons (always override). Phone number is NOT a location signal (portability broke circle allocation). Voice: **WhatsApp voice notes for MVP** (`ai4bharat/indic-conformer-600m-multilingual` ASR, all 22 langs, MIT; `ai4bharat/indic-parler-tts` TTS, 21 langs — both verified current 2026-09-03); **telephony IVR deferred to Phase 3** — its real justification is reaching people with no smartphone, but it's a live-demo risk and voice notes get most of the benefit. New doc `MVP-PLAN.md`: 4-minute pitch script built beat by beat, 14-item build sheet, 6-person lane split, 4-week sequencing, demo-ops/cache-warming, and Q&A prep for the four questions judges will ask.

- **2026-09-01 — Phase 3 build & verify.** Gemini 3.1 Pro, Antigravity IDE. Added Gemini generation and extraction capabilities using `langchain-google-genai`. Set up outcome-based caching in SQLite by hashing identical scheme match structures instead of continuous user input variables to improve hit rates. Adjusted graph flow and updated the testing suite to support async invocation across the LangGraph checkpointer. Resolved coroutine invocation limits and test lifecycles. 72/72 tests passing.
- **2026-09-01 — Phase 2 build & verify.** Gemini 3.1 Pro, Antigravity IDE. Resumed cut-off session that half-implemented Phase 2. Wired up `src/worker.py` to correctly route between button and text messages based on the graph's `response_content_sid`. Wrote `test_buttons.py` and caught state initialization issue in LangGraph testing. Verified dual-mode fallback logic (buttons when possible, text for Sandbox/unsupported). 66/66 tests passing.
- **2026-08-31 — Phase 1 build.** Built schemes.py (Tier 1 eligibility engine), calculator.py (EMI with 3 moratorium treatments), rewrote graph.py (intake flow). Removed unverified age fields from config.py. Created test_schemes.py (26 tests) and test_calculator.py (23 tests). Fixed calculator edge case (zero moratorium). Final: 62/62 tests passing, Phase 0 held.
- **2026-08-30 — Phase 0 verification.** Ran full test suite: 13/13 passing. Phase 0 verified complete. Phase 1 implementation plan created. Planning docs saved to `docs/` directory.
- **2026-08-30 — Phase 0 build session.** All Phase 0 files created and committed. Initial commit.
- **2026-08-29 — Planning session.** No code. Produced the full doc suite. Handing off to Sunday's build session.
