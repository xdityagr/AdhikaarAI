"""
Financial literacy — deterministic templates, no LLM.

"Enhance financial literacy among the target demographic regarding concessional
lending" is one of the PS's two stated impact goals, and a recommender plus an
EMI number does not satisfy it.

Everything here is a pure function over an EMIResult or an EligibilityResult.
Nothing calls a model, so nothing can hallucinate a rupee figure, nothing needs
caching, and every line renders instantly on a slow connection. That is a
deliberate design choice, not a shortcut — these numbers are the ones a person
will make a borrowing decision on.

WhatsApp formatting: *bold* (single asterisk), not Markdown **bold**.
"""

from __future__ import annotations

from src.calculator import EMIResult
from src.config import get_settings
from src.schemes import (
    EligibilityResult,
    SchemeMatch,
    format_rupees as _rupees,
    notable_rejections,
)


def format_true_cost(emi: EMIResult) -> str:
    """What the loan actually costs — not the instalment, the total.

    Most applicants are quoted an instalment and never see the total they will
    repay before they sign. This is the single number that changes how someone
    thinks about a loan.
    """
    return (
        f"*What this loan really costs*\n"
        f"You borrow: {_rupees(emi.loan_amount)}\n"
        f"You repay: {_rupees(emi.total_payable)} over {emi.tenure_months // 12} years\n"
        f"So the loan costs you: *{_rupees(emi.total_interest)}*"
    )


def format_instalment(emi: EMIResult) -> str:
    """The real instalment, plus a monthly figure to budget against.

    NSFDC repays quarterly. Quoting only a monthly EMI would be a number the
    borrower is never actually asked to pay — so show both, and say which is which.
    """
    lines = [
        f"*Your repayment*",
        f"{emi.instalment_frequency.capitalize()}: {_rupees(emi.instalment_amount)} "
        f"× {emi.instalment_count} instalments",
        f"(set aside about {_rupees(emi.monthly_equivalent)} a month)",
    ]
    if emi.moratorium_months > 0:
        lines.append(
            f"First {emi.moratorium_months} months: {_rupees(emi.moratorium_instalment)} "
            f"per instalment — interest only."
        )
    return "\n".join(lines)


def format_moneylender_comparison(
    emi: EMIResult,
    monthly_rate_pct: float | None = None,
) -> str:
    """The highest-impact message in the product.

    The real alternative for this borrower is not another bank — it is an
    informal lender at 3-10% *per month*. Until you put the two side by side,
    "6.5% per year" is an abstraction.

    Model: interest-only at r% per month over the same repayment period, with
    the principal repaid at the end. That is how informal lending in this
    segment usually works, and stating the model out loud means a challenge gets
    an answer instead of a shrug.
    """
    if monthly_rate_pct is None:
        monthly_rate_pct = get_settings().moneylender_monthly_rate_pct

    months = emi.repayment_months
    informal_interest = emi.loan_amount * (monthly_rate_pct / 100.0) * months
    difference = informal_interest - emi.total_interest

    return (
        f"*Compare this to a local moneylender*\n"
        f"This scheme, at {emi.rate_annual}% a year: "
        f"interest of *{_rupees(emi.total_interest)}*\n"
        f"A moneylender at {monthly_rate_pct:g}% a month: "
        f"interest of *{_rupees(informal_interest)}*\n\n"
        f"On the same {_rupees(emi.loan_amount)}, over the same {months} months, "
        f"this scheme saves you about *{_rupees(difference)}*.\n"
        f"_Assumes interest paid monthly and the principal repaid at the end — "
        f"the usual local arrangement._"
    )


def format_moratorium_strip(emi: EMIResult) -> str:
    """Explain a moratorium in cash-flow terms, because nobody knows the word."""
    if emi.moratorium_months <= 0:
        return ""
    return (
        f"*What the grace period means*\n"
        f"Months 1-{emi.moratorium_months}: you pay "
        f"{_rupees(emi.moratorium_instalment)} per instalment (interest only).\n"
        f"After that: {_rupees(emi.instalment_amount)} per instalment.\n"
        f"_A grace period is not free — interest still builds during it._"
    )


def format_why_not(result: EligibilityResult, limit: int = 2) -> str:
    """Explain the schemes that did NOT match.

    Explaining the rejections is what actually teaches someone the rules —
    "Term Loan starts at ₹1.40 lakh" is a fact they keep.
    """
    rejections = notable_rejections(result, limit=limit)
    if not rejections:
        return ""
    lines = ["*Not a match for you right now*"]
    lines.extend(f"• {r.reason}" for r in rejections)
    return "\n".join(lines)


def format_why_eligible(match: SchemeMatch) -> str:
    """The positive half of the trail — the arithmetic, shown."""
    return f"*Why you qualify for {match.name}*\n{match.why_eligible}"


def format_fraud_shield() -> str:
    """Middleman extraction is endemic in this channel.

    One line, and it belongs on every recommendation. Note the deliberate
    precision: the government charges nothing. If we ever charge for assisted
    filing, that is us, it is optional, and the free path stays visible.
    """
    return (
        "⚠️ *NSFDC never charges a fee to apply.* "
        "If anyone asks you for money to process or approve your loan, that is fraud. "
        "You can apply yourself, free, through a channel partner."
    )


def format_priority_note(scheme_priority: dict[str, float] | None, gender: str) -> str:
    """Tell someone when they're in a priority category — nobody does today."""
    if not scheme_priority:
        return ""
    share = scheme_priority.get("women")
    if share and gender == "female":
        return (
            f"_You're in a priority group: NSFDC targets {share:.0%} of this scheme's "
            f"funds for women applicants._"
        )
    return ""


def format_scheme_comparison(
    priced: list[tuple[SchemeMatch, "EMIResult"]],
    limit: int = 3,
) -> str:
    """Compare the schemes a person qualifies for, by what they actually cost.

    This is the sharpest form the "same project, different price" idea takes,
    and it needs no partner data at all. A ₹1.2 lakh tailoring unit qualifies for
    the Micro Finance Scheme at 6.5% AND the Aajeevika Micro-Finance Yojana at
    15% — the same money, the same project, 8.5 percentage points apart, both
    published by NSFDC.

    Nobody tells applicants this. Being routed to the wrong one of two schemes
    you equally qualify for is a pure, invisible loss.
    """
    if len(priced) < 2:
        return ""

    ranked = sorted(priced, key=lambda pair: pair[1].total_interest)
    cheapest_match, cheapest_emi = ranked[0]
    dearest_match, dearest_emi = ranked[-1]
    if dearest_emi.total_interest <= cheapest_emi.total_interest:
        return ""

    lines = ["*You qualify for more than one — they don't cost the same*"]
    for match, emi in ranked[:limit]:
        marker = " ← cheapest" if match.scheme_id == cheapest_match.scheme_id else ""
        lines.append(
            f"• {match.name} at {emi.rate_annual:g}%: "
            f"{_rupees(emi.total_interest)} interest{marker}"
        )

    difference = dearest_emi.total_interest - cheapest_emi.total_interest
    lines.append(
        f"\nChoosing {cheapest_match.name} over {dearest_match.name} saves you "
        f"*{_rupees(difference)}* on the same project."
    )
    return "\n".join(lines)
