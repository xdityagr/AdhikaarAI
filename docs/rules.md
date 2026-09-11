# rules.md — Scheme eligibility & financial parameters
Every number below is a config value, not a hardcoded constant, for a reason: these figures have genuinely disagreed across five independent sources so far (the PS text itself, a direct nsfdc.nic.in fetch, and three separate research passes), including two that resolved themselves as unreliable. **Do not add a sixth research pass on this — it hasn't converged and won't. Resolution comes from Monday's SPOC meeting or a direct call to an SCA/NSFDC contact, not more search.**

Defaults below use the PS's own stated numbers, since that's literally what you're evaluated against. Update this file, not the code, once verified numbers come back.

## Config block (drop into your actual config module)

```python
# CONFIDENCE: PS-stated (authoritative for judging) — cross-check before finale, not before internals
SCHEMES = {
    "MICRO_FINANCE": {
        "name": "Micro Finance Scheme",
        "max_project_cost": 140_000,
        "financing_pct": 0.90,
        "rate_min": 6.5, "rate_max": 8.0,      # PS "Background" section figure
        "moratorium_months_min": 3, "moratorium_months_max": 12,
        "max_income": 500_000,
    },
    "TERM_LOAN": {
        "name": "Term Loan",
        "max_project_cost": 5_000_000,
        "financing_pct": 0.90,
        "rate_min": 6.5, "rate_max": 15.0,     # PS "Expected Solution" section figure — wider range than Background section; scheme is tiered by loan size per every source, exact breakpoints unresolved
        "moratorium_months_min": 3, "moratorium_months_max": 12,
        "max_income": 500_000,
    },
    "EDUCATIONAL_LOAN": {
        "name": "Educational Loan Scheme",
        "max_project_cost": None,               # PS doesn't state a ceiling; third-party figures range ₹10L-₹40L, unresolved
        "financing_pct": 0.90,
        "rate_min": 6.5, "rate_max": 8.0,
        "moratorium_months_min": 3, "moratorium_months_max": 12,
        "max_income": 500_000,
        "women_rebate_pct": 0.5,                 # consistent across every source checked — this one's solid
    },
}

# CONFIDENCE: verified directly against nsfdc.nic.in — more specific than the PS text, use if you want the tiered-rate story for the pitch, but don't silently contradict the PS numbers above without explaining why in the demo
NSFDC_DIRECT_VERIFICATION = {
    "TERM_LOAN_ALT": {"partner_rate": 4.0, "beneficiary_rate": 8.0, "tenure_years": 7, "moratorium_months": 6},
    "UTKARSH_LOAN": {  # possibly a distinct product from Term Loan, not just a tier of it — unresolved
        "min_project_cost": 1_000_000, "max_project_cost": 5_000_000,
        "beneficiary_rate": 9.0, "financing_pct": 0.90, "tenure_years": 7, "moratorium_months": 6,
    },
    "EDUCATIONAL_LOAN_ALT": {"partner_rate": 1.5, "beneficiary_rate": 4.0, "women_rebate_pct": 0.5,
                              "tenure_years": 7, "moratorium_months": 6},
}
```

## Prudential norms — Tier 3 (high confidence, corroborated across every source including the negative finding below)

```python
PRUDENTIAL_NORMS = {
    "SCA":  {"requires": "cumulative_utilization >= 1.0 AND has_active_overdues == False"},
    "RRB":  {"requires": "net_npa_percentage < 15.0 in at least 3 of preceding 6 financial years, AND net profit in at least 3 of those 6 years"},
}
```

**Confirmed (negative finding, worth stating in the pitch, not hiding):** no source — not NSFDC, not data.gov.in, not RBI — publishes a live public API for branch-level NPA/utilization data. Central monitoring is periodic, not real-time. This is *why* Tier 3's live data is mocked, not a gap in your research.

## Real seed data for `channel_partners` (names are real institutions, not fabricated — the numbers attached to them in the table are what's mocked)

| State | Known SCA |
|---|---|
| Maharashtra | Mahatma Phule Backward Class Development Corporation (MPBCDC) |
| Tamil Nadu | Tamil Nadu Adi Dravidar Housing and Development Corporation (TAHDCO) |
| West Bengal | West Bengal SC ST Development and Finance Corporation |
| Andhra Pradesh | Andhra Pradesh Scheduled Castes Co-operative Finance Corporation |

Expand this list from each state's own SC/backward-class development corporation site as time allows — it's a real, findable dataset, just not one anyone has fully compiled online yet.

## Team quota / process facts (confirmed, not scheme-related, kept here since this is the "verified facts" file)
- MUJ internal-round quota: 45 primary + 5 waitlisted teams (per direct prior experience — reconfirm at Monday's meeting, can shift year to year).
- National, regardless of institution: 6-member teams, at least 1 female member, max 2 problem statements per team.
