# architecture.md — SIH26092 Backend
Technical spec only. For business context/judging strategy see prd.md. For scheme numbers see rules.md. For bot copy see phrases.md.

## Stack
Python, FastAPI, LangGraph. SQLite (WAL mode) for all storage — no hosted DB needed at this scale. On connection open, set: `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`, `foreign_keys=ON`. WAL lets readers and writers stop blocking each other; the 5-second busy timeout means concurrent writers queue and retry instead of throwing `SQLITE_BUSY` mid-demo. Gemini as primary model; OpenRouter (DeepSeek/Kimi K2/GLM-4.5-Air) as fallback; AI4Bharat IndicTrans2 as the translation bridge. WhatsApp delivery via Twilio Sandbox (dev/demo) → Meta Cloud API (target). Deploy target: EC2 (reuse the SHIELD deployment pattern), not a dev tunnel, before finale.

## Non-negotiables (these fixed GrantBot's actual prior failures — do not regress on them)
1. Webhook handler does ONLY: verify HMAC-SHA256 signature → check idempotency (message_id already processed?) → enqueue → return `200` immediately. No LLM calls, no slow work, inside the handler. Ever.
2. Conversation state (where a user is in the flow) is read and written atomically, in the same transaction, from one single source of truth. Use LangGraph's own checkpointer (`langgraph.checkpoint.sqlite.SqliteSaver`, keyed by `thread_id` per user) — not a hand-rolled state table — this is purpose-built for exactly this and removes a whole bug class.
3. Every worker step is idempotent and retryable. A crash or timeout mid-processing must be safe to retry, never double-process or corrupt state.
4. Structured input (WhatsApp buttons/lists/Flows) is the primary path for anything with a fixed answer set. Free-text LLM extraction is the fallback path, not the default — this is the other core fix, since it removes "the AI didn't understand me" as a failure mode for the load-bearing intake fields.

## The message chain (build and test this before anything else)
1. Message arrives → webhook (see Non-negotiable #1) → queue.
2. Worker reads user state atomically (LangGraph checkpointer, see #2).
3. Route on state: mid-Flow/button response → skip straight to step 4 with structured data, no LLM call. Free text → Tier 2 extraction (below) first.
4. Tier 1 (deterministic rules engine, rules.md) evaluates eligibility. Pure computation, no API call.
5. Generation: check `recommendation_cache` (keyed on profile fingerprint + language) before calling any LLM. Cache hit → done. Cache miss → call Gemini, cache the result.
6. State written back atomically, same transaction as the read in step 2.
7. Response sent via a separate outbound WhatsApp API call, decoupled from the original webhook request.

## Three-tier recommendation pipeline
- **Tier 1 — deterministic eligibility.** Boolean rules against the config in rules.md: income, project cost, category, age. No API call. 100% precision on boundary cases (a judge WILL test income exactly at the threshold).
- **Tier 2 — light semantic matching, free text only.** When a user describes their project in their own words instead of using buttons, map that description to a structured project-type field. Keep this lightweight (keyword matching or a small embedding lookup) — it feeds Tier 1, it never overrides Tier 1's numeric decision.
- **Tier 3 — prudential/geo routing.** See below.

## Tier 3 — partner locator + prudential routing
Real rule, mocked live data — build the filter logic for real:
- SCA: exclude if `cumulative_utilization < 1.0` or `has_active_overdues`.
- RRB: exclude if `net_npa_percentage >= 15.0`.
- Distance: Haversine, default 50km radius. Get lat/long from WhatsApp's native location-share (preferred, zero cost, no geocoding) or a PIN-code-to-coordinates lookup as fallback for typed input.
- Seed `channel_partners` with real institution names (e.g. TAHDCO, MPBCDC, West Bengal SC ST Development and Finance Corporation) and mocked-but-clearly-labeled `utilization_flag`/`net_npa_percentage` values. Comment the mock clearly in code — this is a talking point, not something to hide.

```python
class ChannelPartnerBranch(BaseModel):
    branch_id: str; name: str
    agency_type: str  # "SCA", "PSB", "RRB", "NBFC-MFI"
    latitude: float; longitude: float
    net_npa_percentage: float  # mocked
    cumulative_utilization: float  # mocked
    has_active_overdues: bool  # mocked

def find_viable_partners(user_lat, user_lon, branches, radius_km=50.0):
    viable = []
    for b in branches:
        if b.agency_type == "SCA" and (b.cumulative_utilization < 1.0 or b.has_active_overdues):
            continue
        if b.agency_type == "RRB" and b.net_npa_percentage >= 15.0:
            continue
        d = haversine_km(user_lat, user_lon, b.latitude, b.longitude)
        if d <= radius_km:
            viable.append({"branch_id": b.branch_id, "name": b.name,
                            "agency_type": b.agency_type, "distance_km": round(d, 2)})
    return sorted(viable, key=lambda x: x["distance_km"])
```

## Calculator
Pure computation, no LLM. Rate lookup is scheme-tiered (see rules.md — do not hardcode rates here, import from config). Support three moratorium treatments since different schemes use different ones: simple-interest-during-moratorium (default), capitalized-interest (unpaid interest folded into principal before recalculating EMI), and government-subvention (₹0 during moratorium — only relevant if scope expands beyond the PS's three named schemes).

## Model strategy
1. **Gemini (primary).** Flash-Lite for Tier-2 extraction (lighter task, higher free RPD). Flash/Pro for generation, only on a cache miss. Verify exact current free-tier RPM/RPD against the live AI Studio dashboard before relying on any specific number — Google has been iterating fast (2.0 retiring, 3.x rolling out) and the exact figures move.
2. **OpenRouter fallback**, on Gemini 429/failure. DeepSeek, Kimi K2, GLM-4.5-Air are free there. **Before this goes live: turn on "ZDR Endpoints only" and disable "free endpoints that may train on inputs" in OpenRouter's account privacy settings.** Sensitive fields (income, category) should never transit a model that isn't confirmed zero-retention.
3. **Translation bridge.** For regional-language output when Gemini isn't available: generate in English via the fallback model, translate with AI4Bharat's IndicTrans2 (MIT-licensed, ~1-1.1B param distilled variant). Deploy this as a persistent CPU-hosted service (EC2, or a persistent Colab/Kaggle session) — do NOT use a Hugging Face Spaces ZeroGPU endpoint for this in a live demo; cold-start latency there is a real failure risk against WhatsApp's tight webhook timeout.
4. **Don't train or fine-tune anything.** The eligibility decision is Tier 1's job, not the model's.

## Data model
SQLite, WAL mode.
- `users(user_id PK, preferred_language, created_at, last_active_at)`
- `conversation_state` — handled by LangGraph's checkpointer, not a custom table (see Non-negotiable #2)
- `processed_messages(message_id PK, processed_at)` — idempotency guard
- `recommendation_cache(profile_fingerprint, language, scheme_id, explanation, PK(fingerprint, language))`
- `schemes(scheme_id PK, ...)` — loaded from rules.md's config, not hardcoded
- `channel_partners(partner_id PK, name, agency_type, state, district, latitude, longitude, net_npa_percentage, cumulative_utilization, has_active_overdues)`

## WhatsApp integration
Structured input (buttons/lists/Flows) over free text wherever the answer set is fixed. Sandbox for dev/demo now; Meta's direct Cloud API is the closer-to-production route — usage is entirely reactive (beneficiary messages first), so it should fall inside the free 24-hour service window with no per-message cost. One shared service layer behind both WhatsApp and the eventual web backend — never two implementations of the same logic. Language selection via buttons at the start, not auto-detection.

## Security
- Verify webhook signatures (HMAC-SHA256) before trusting any payload.
- No API key ever committed to the repo — it's public; double-check, rotate if needed.
- Explicit consent before collecting category/income (one WhatsApp message at start is enough — see phrases.md for the actual copy).
- No plaintext logging of sensitive fields beyond what's operationally needed.
- Rate-limit the webhook endpoint itself, separately from LLM-call rate limiting.
- Rate-limit per user too — protects against a state-machine bug causing a message loop from silently burning the day's API quota.

## Build order
Phase 0 (before internals), in this sequence: (1) webhook→queue→worker skeleton with idempotency + LangGraph checkpointer state — prove this is solid before anything else — (2) Tier 1 + calculator on rules.md's numbers — (3) WhatsApp Flow for structured intake — (4) Gemini wired in for Tier 2 + generation, caching from day one — (5) Tier 3 with real rule logic + mocked data, clearly commented — (6) language-select buttons. Stages 1-2 alone are the internal-round safety net if time runs short.
