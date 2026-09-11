"""
Tier 1 — Deterministic eligibility engine.

Pure-function scheme matching: no I/O, no side effects, no LLM. Evaluates user
profiles against the scheme corpus (corpus/v1/schemes.json).

Architecture.md requirement: 100% precision on boundary cases.
A judge WILL test income exactly at ₹5,00,000.

Key design decisions:
- Income/cost checks use ≤ (not <) — income == 500_000 MUST match
- No age gating. This used to be "unconfirmed"; nsfdc.nic.in/eligibility-requirements
  states no age condition at all, so the absence is now confirmed.
- Category check: the PS explicitly targets SC beneficiaries — but a non-SC user
  gets a referral to the right corporation, never a dead end.
- Project type comes from the corpus, per scheme. It is NOT a module-level map
  here any more: a scheme missing from that map silently matched every project
  type, which is how Udyam Nidhi (a business loan) started being offered to
  education applicants the moment the corpus grew past three schemes.

Rejections are first-class. Explaining why a scheme did NOT match is what turns
a recommender into a financial-literacy tool, and it is one of the PS's two
stated impact goals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.config import SCHEMES

# Other national corporations running the same channel-finance structure for
# other target groups. Used for the No-Dead-Ends referral (PRD-v3 §5.2) so an
# out-of-category user is handed onward instead of rejected.
CORPORATION_BY_CATEGORY: dict[str, str] = {
    "ST": "NSTFDC (National Scheduled Tribes Finance and Development Corporation)",
    "OBC": "NBCFDC (National Backward Classes Finance and Development Corporation)",
    "BC": "NBCFDC (National Backward Classes Finance and Development Corporation)",
    "MINORITY": "NMDFC (National Minorities Development and Finance Corporation)",
    "SAFAI_KARAMCHARI": "NSKFDC (National Safai Karamcharis Finance and Development Corporation)",
    "PWD": "NHFDC (National Handicapped Finance and Development Corporation)",
}


# ---------------------------------------------------------------------------
# User profile — validated input to the eligibility engine
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    """Beneficiary profile for scheme eligibility evaluation.

    Every field comes from the intake flow (graph.py) or WhatsApp Flow.
    Category defaults to "SC" since the PS explicitly targets SC beneficiaries.

    Deliberately NO age field — nsfdc.nic.in publishes no age condition.

    `annual_income` is FAMILY income from all sources, which is what NSFDC's
    ₹5 lakh ceiling is assessed against. The field name is kept for
    compatibility; the intake prompt is what makes the distinction clear, since
    in a multi-earner household people routinely answer with their own income.
    """
    project_type: str = Field(description="'business' or 'education'")
    project_cost: float = Field(ge=0, description="Estimated project cost in ₹")
    annual_income: float = Field(ge=0, description="Family annual income from all sources in ₹")
    category: str = Field(default="SC", description="Social category (SC for this PS)")
    gender: str = Field(default="male", description="'male', 'female', or 'other'")
    education_status: str = Field(
        default="unknown",
        description="'below_10th', '10th_to_12th', 'graduate_plus', or 'unknown'",
    )

    @field_validator("project_type")
    @classmethod
    def validate_project_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("business", "education"):
            raise ValueError(f"project_type must be 'business' or 'education', got '{v}'")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("male", "female", "other"):
            raise ValueError(f"gender must be 'male', 'female', or 'other', got '{v}'")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("education_status")
    @classmethod
    def validate_education_status(cls, v: str) -> str:
        v = v.strip().lower()
        allowed = ("below_10th", "10th_to_12th", "graduate_plus", "unknown")
        if v not in allowed:
            raise ValueError(f"education_status must be one of {allowed}, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class SchemeMatch:
    """Result of a successful scheme eligibility evaluation."""
    scheme_id: str
    name: str
    why_eligible: str              # Human-readable explanation
    rate_min: float
    rate_max: float
    max_project_cost: Optional[float]
    financing_pct: float
    women_rebate_pct: float = 0.0
    # Fields below are appended with defaults so existing consumers
    # (cache.generate_fingerprint, llm.py, graph.py) are unaffected.
    rate_by_partner_type: dict[str, float] = field(default_factory=dict)
    tenure_months: int = 84
    moratorium_months: int = 6
    periods_per_year: int = 12
    repayment_frequency: str = "MONTHLY"
    max_loan: Optional[float] = None


@dataclass
class SchemeRejection:
    """Why one scheme did NOT match — the other half of the Why/Why-Not trail.

    `rule` is a stable machine-readable tag; `reason` is the user-facing
    sentence. Tests assert on `rule` so that rewording the copy for the demo
    doesn't break the suite.
    """
    scheme_id: str
    name: str
    reason: str
    rule: str  # CATEGORY | PROJECT_TYPE | INCOME | COST_CEILING | COST_FLOOR


@dataclass
class EligibilityResult:
    matches: list[SchemeMatch] = field(default_factory=list)
    rejections: list[SchemeRejection] = field(default_factory=list)
    category_note: str = ""   # No-Dead-Ends referral; "" when the category is SC


# ---------------------------------------------------------------------------
# The Tier 1 engine
# ---------------------------------------------------------------------------

def format_rupees(amount: float) -> str:
    """Indian digit grouping: 12,34,567 — not 1,234,567.

    Lives here rather than in literacy.py because schemes.py is the lower layer
    and literacy imports it; the other direction would be a cycle. Every rupee
    figure shown to a user goes through this, so they all group the same way.
    """
    whole = int(round(amount))
    s = str(abs(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"₹{'-' if whole < 0 else ''}{s}"


# Internal alias kept short for the reason strings below.
_rupees = format_rupees


def evaluate_eligibility(profile: UserProfile) -> EligibilityResult:
    """Evaluate a profile against every scheme, capturing matches AND rejections.

    Pure function — no I/O, no side effects, no LLM. Reads the corpus only.

    Checks, in order:
    1. Category — must be SC (PS requirement). Non-SC gets a referral, not a wall.
    2. Project type — from the corpus, per scheme.
    3. Annual family income — must be ≤ max_income (NOT <, boundary-critical).
    4. Project cost — must sit within the scheme's floor and ceiling.
    """
    result = EligibilityResult()

    # Category — the one global check. A non-SC applicant isn't rejected five
    # times over; they're pointed at the corporation that does serve them.
    if profile.category != "SC":
        corporation = CORPORATION_BY_CATEGORY.get(profile.category)
        if corporation:
            result.category_note = (
                f"NSFDC schemes are for Scheduled Caste applicants. For your category, "
                f"the equivalent schemes are run by {corporation}."
            )
        else:
            result.category_note = (
                "NSFDC schemes are for Scheduled Caste applicants. Other national "
                "corporations run similar schemes for ST, OBC, minority, safai karamchari "
                "and disability categories."
            )
        return result

    for scheme_id, scheme in SCHEMES.items():
        name = scheme["name"]

        # Project type — sourced from the corpus, never defaulted.
        project_types = scheme.get("project_types") or []
        if profile.project_type not in project_types:
            result.rejections.append(SchemeRejection(
                scheme_id=scheme_id,
                name=name,
                rule="PROJECT_TYPE",
                reason=f"{name} is for {' and '.join(project_types)} purposes.",
            ))
            continue

        # Income — ≤, not < (boundary-critical: a judge WILL test 500000)
        max_income = scheme["max_income"]
        if profile.annual_income > max_income:
            result.rejections.append(SchemeRejection(
                scheme_id=scheme_id,
                name=name,
                rule="INCOME",
                reason=(
                    f"Your family income of {_rupees(profile.annual_income)} is above the "
                    f"{_rupees(max_income)} limit for {name}."
                ),
            ))
            continue

        # Project cost floor — Term Loan starts at ₹1.40 lakh. This is the check
        # that produces the demo's Why-Not line.
        min_cost = scheme.get("min_project_cost")
        if min_cost is not None and profile.project_cost < min_cost:
            result.rejections.append(SchemeRejection(
                scheme_id=scheme_id,
                name=name,
                rule="COST_FLOOR",
                reason=(
                    f"{name} starts at {_rupees(min_cost)} — your project is "
                    f"{_rupees(profile.project_cost)}."
                ),
            ))
            continue

        # Project cost ceiling
        max_cost = scheme.get("max_project_cost")
        if max_cost is not None and profile.project_cost > max_cost:
            result.rejections.append(SchemeRejection(
                scheme_id=scheme_id,
                name=name,
                rule="COST_CEILING",
                reason=(
                    f"{name} covers projects up to {_rupees(max_cost)} — yours is "
                    f"{_rupees(profile.project_cost)}."
                ),
            ))
            continue

        # ---- eligible: build the "why" explanation ----
        why_parts: list[str] = [
            f"Your annual income ({_rupees(profile.annual_income)}) "
            f"is within the {format_rupees(max_income)} limit"
        ]
        if max_cost is not None:
            why_parts.append(
                f"Your project cost ({_rupees(profile.project_cost)}) "
                f"is within the {format_rupees(max_cost)} ceiling"
            )
        else:
            why_parts.append("No project cost ceiling for this scheme")

        women_rebate = scheme.get("women_rebate_pct", 0.0)
        applied_rebate = women_rebate if profile.gender == "female" else 0.0
        if applied_rebate > 0:
            why_parts.append(f"Women's rebate of {applied_rebate}% on interest rate applies")

        result.matches.append(SchemeMatch(
            scheme_id=scheme_id,
            name=name,
            why_eligible=". ".join(why_parts) + ".",
            rate_min=scheme["rate_min"],
            rate_max=scheme["rate_max"],
            max_project_cost=max_cost,
            financing_pct=scheme["financing_pct"],
            women_rebate_pct=applied_rebate,
            rate_by_partner_type=dict(scheme.get("rate_by_partner_type", {})),
            tenure_months=scheme.get("tenure_months", 84),
            moratorium_months=scheme.get("moratorium_months", 6),
            periods_per_year=scheme.get("periods_per_year", 12),
            repayment_frequency=scheme.get("repayment_frequency", "MONTHLY"),
            max_loan=scheme.get("max_loan"),
        ))

    return result


def evaluate_eligible_schemes(profile: UserProfile) -> list[SchemeMatch]:
    """Backwards-compatible view: matches only.

    Prefer evaluate_eligibility(), which also carries the rejections and the
    No-Dead-Ends referral. Kept because cache.generate_fingerprint, llm.py and
    graph.py all consume list[SchemeMatch] and have no use for rejections.
    """
    return evaluate_eligibility(profile).matches


def notable_rejections(
    result: EligibilityResult,
    limit: int = 2,
) -> list[SchemeRejection]:
    """The rejections worth showing a user.

    PROJECT_TYPE rejections are dropped: someone who asked for a business loan
    does not need to be told the education loan is for education. What teaches
    them something is a threshold they missed — "Term Loan starts at ₹1.40 lakh".
    """
    informative = [r for r in result.rejections if r.rule != "PROJECT_TYPE"]
    priority = {"COST_FLOOR": 0, "COST_CEILING": 1, "INCOME": 2}
    informative.sort(key=lambda r: priority.get(r.rule, 9))
    return informative[:limit]
