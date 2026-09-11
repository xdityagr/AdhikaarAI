"""
Corpus models — Plane A.

Typed, validated shapes for the scheme corpus. These are the ONLY values the
eligibility engine, calculator and router are allowed to reason over. Narrative
content (Plane B: purpose, FAQs, document lists) is deliberately not modelled
here — see docs/data-sources.md §2.2 for the reasoning, but in short: a model
may quote Plane B, it may never decide from it, and keeping them in separate
types is what makes that rule enforceable rather than aspirational.

Validation is strict on purpose. A malformed corpus should fail loudly at import
with a message naming the bad field, not silently produce a wrong interest rate
three screens into a conversation.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CorpusError(RuntimeError):
    """Raised when the corpus is missing, malformed, or internally inconsistent."""


ProjectType = Literal["business", "education"]
RepaymentFrequency = Literal["MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUAL"]

# How many instalments a year each published frequency implies.
PERIODS_PER_YEAR: dict[str, int] = {
    "MONTHLY": 12,
    "QUARTERLY": 4,
    "HALF_YEARLY": 2,
    "ANNUAL": 1,
}

# The rate key used where NSFDC publishes one rate for every partner category.
DEFAULT_RATE_KEY = "DEFAULT"


class MoratoriumVariant(BaseModel):
    condition: str
    moratorium_months: int = Field(ge=0)
    note: str = ""


class SchemeFinance(BaseModel):
    min_project_cost: Optional[float] = Field(default=None, ge=0)
    max_project_cost: Optional[float] = Field(default=None, ge=0)
    max_loan: Optional[float] = Field(default=None, ge=0)
    financing_pct: float = Field(gt=0, le=1)
    intermediary_rate: Optional[float] = Field(default=None, ge=0, le=30)
    beneficiary_rate_by_partner_type: dict[str, float]
    tenure_months: int = Field(gt=0)
    repayment_frequency: RepaymentFrequency
    moratorium_months: int = Field(ge=0)
    moratorium_variants: list[MoratoriumVariant] = Field(default_factory=list)
    moratorium_note: str = ""
    women_rebate_pct: Optional[float] = Field(default=None, ge=0, le=5)
    security_requirements: Optional[str] = None

    @field_validator("beneficiary_rate_by_partner_type")
    @classmethod
    def validate_rates(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("beneficiary_rate_by_partner_type must not be empty")
        for key, rate in v.items():
            if not 0 <= rate <= 30:
                raise ValueError(f"beneficiary rate for '{key}' out of range 0-30: {rate}")
        return v

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> "SchemeFinance":
        if self.moratorium_months >= self.tenure_months:
            raise ValueError("moratorium_months must be less than tenure_months")
        lo, hi = self.min_project_cost, self.max_project_cost
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"min_project_cost ({lo}) exceeds max_project_cost ({hi})")
        return self

    @property
    def periods_per_year(self) -> int:
        return PERIODS_PER_YEAR[self.repayment_frequency]

    @property
    def rate_min(self) -> float:
        return min(self.beneficiary_rate_by_partner_type.values())

    @property
    def rate_max(self) -> float:
        return max(self.beneficiary_rate_by_partner_type.values())

    @property
    def has_partner_rate_spread(self) -> bool:
        """True when the borrower's rate depends on which partner processes it.

        Only Udyam Nidhi does this today (13% via a cooperative bank, 15% via a
        small finance bank). It is what makes the Cheapest Route feature real —
        and why that feature must stay silent for the other four schemes rather
        than inventing a spread that isn't published.
        """
        return self.rate_min != self.rate_max

    def rate_for_partner_type(self, partner_type: Optional[str]) -> float:
        """Beneficiary rate for a partner category, falling back to DEFAULT."""
        rates = self.beneficiary_rate_by_partner_type
        if partner_type and partner_type in rates:
            return rates[partner_type]
        if DEFAULT_RATE_KEY in rates:
            return rates[DEFAULT_RATE_KEY]
        return self.rate_min


class SchemeRouting(BaseModel):
    eligible_partner_types: list[str] = Field(default_factory=list)
    channel_capability: Literal["FULLY_REMOTE", "HYBRID", "PRESENCE_MANDATORY"] = "PRESENCE_MANDATORY"
    priority_allocation: Optional[dict[str, float]] = None


class Scheme(BaseModel):
    scheme_code: str
    name: str
    short_name: str = ""
    status: Literal["ACTIVE", "SUSPENDED", "CLOSED"] = "ACTIVE"
    project_types: list[ProjectType]
    finance: SchemeFinance
    routing: SchemeRouting

    @field_validator("project_types")
    @classmethod
    def project_types_required(cls, v: list[str]) -> list[str]:
        """A scheme with no project types would match EVERY applicant.

        The previous implementation kept this mapping in a module-level dict in
        schemes.py and treated a missing entry as "matches anything" — so adding
        a scheme without remembering to update the dict silently offered business
        loans to education applicants. Making it a required corpus field turns
        that class of bug into a load-time error.
        """
        if not v:
            raise ValueError("project_types must not be empty — an empty list matches every applicant")
        return v


class SharedEligibility(BaseModel):
    category: list[str]
    max_family_income: float = Field(gt=0)
    income_basis: str
    income_effective_date: str
    income_applies_to: list[str] = Field(default_factory=list)
    income_note: str = ""
    applicant_types: list[str] = Field(default_factory=list)
    all_members_must_qualify: bool = True
    age: Optional[dict] = None
    requires_caste_certificate: bool = True
    direct_application_permitted: bool = False


class Provenance(BaseModel):
    source_url: str
    supporting_urls: list[str] = Field(default_factory=list)
    fetched_at: str
    confidence: Literal["OFFICIAL", "PS-STATED", "DERIVED", "MOCKED", "TO_VERIFY"]
    review_note: str = ""


class Corpus(BaseModel):
    corpus_version: str
    corporation: str
    generated_at: str
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance
    shared_eligibility: SharedEligibility
    schemes: list[Scheme]

    @field_validator("schemes")
    @classmethod
    def schemes_unique_and_present(cls, v: list[Scheme]) -> list[Scheme]:
        if not v:
            raise ValueError("corpus contains no schemes")
        codes = [s.scheme_code for s in v]
        dupes = {c for c in codes if codes.count(c) > 1}
        if dupes:
            raise ValueError(f"duplicate scheme_code(s): {sorted(dupes)}")
        return v

    def by_code(self, scheme_code: str) -> Optional[Scheme]:
        for scheme in self.schemes:
            if scheme.scheme_code == scheme_code:
                return scheme
        return None
