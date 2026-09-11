"""
EMI Calculator — pure computation, no LLM.

Supports three moratorium treatments per architecture.md:
1. Simple interest during moratorium (default) — borrower pays interest-only
2. Capitalized interest — unpaid interest added to principal
3. Government subvention — ₹0 during moratorium

Rate lookup comes from scheme config (rules.md), never hardcoded here.
Women's 0.5% rebate for Educational Loan is applied in this module.

Default tenure: 84 months (7 years) from NSFDC direct verification.
Default moratorium: 6 months from NSFDC direct verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MoratoriumType(str, Enum):
    """Moratorium interest treatment."""
    SIMPLE_INTEREST = "simple_interest"   # Borrower pays interest-only during moratorium
    CAPITALIZED = "capitalized"           # Unpaid interest added to principal
    SUBVENTION = "subvention"             # ₹0 during moratorium (govt. subsidized)


# How each supported instalment cadence is described to a user.
_FREQUENCY_LABELS: dict[int, str] = {
    12: "monthly",
    6: "every 2 months",
    4: "quarterly",
    3: "every 4 months",
    2: "half-yearly",
    1: "annual",
}


@dataclass
class EMIResult:
    """Complete EMI calculation result.

    A note on naming. The first six payment fields say "monthly" because that is
    what they meant when this only did monthly EMIs, and existing callers and
    tests depend on them. They now hold the PER-PERIOD value, which is identical
    at the monthly default. New code should prefer the honestly-named fields
    below — `instalment_amount`, `instalment_count`, `monthly_equivalent`.

    This matters because NSFDC does not repay monthly. Every scheme it publishes
    repays QUARTERLY (Udyam Nidhi quarterly or half-yearly), so a monthly figure
    is not what the borrower will actually be asked to pay.
    """
    loan_amount: float                    # Principal (project_cost × financing_pct)
    rate_annual: float                    # Applied annual rate (after any rebate)
    tenure_months: int                    # Total tenure including moratorium
    moratorium_months: int                # Moratorium period
    repayment_months: int                 # Months of actual repayment
    moratorium_type: MoratoriumType
    moratorium_monthly_payment: float     # Per-period payment during moratorium
    emi_after_moratorium: float           # Per-period instalment during repayment
    total_payable: float                  # Total amount paid over entire tenure
    total_interest: float                 # Total interest paid
    # --- appended with defaults; nothing existing has to change ---
    periods_per_year: int = 12
    instalment_frequency: str = "monthly"
    instalment_amount: float = 0.0        # Same as emi_after_moratorium, honestly named
    instalment_count: int = 0             # Number of instalments actually paid
    monthly_equivalent: float = 0.0       # What to budget per month
    moratorium_instalment: float = 0.0    # Same as moratorium_monthly_payment


def _reducing_balance_emi(principal: float, monthly_rate: float, months: int) -> float:
    """Standard reducing-balance EMI formula.

    EMI = P × r × (1+r)^n / ((1+r)^n - 1)

    Where P = principal, r = the rate PER PERIOD, n = number of periods.
    (The parameter names still say monthly/months for compatibility; at the
    monthly default a period is a month.)

    Returns 0.0 for zero periods.
    """
    if months <= 0:
        return 0.0
    if monthly_rate == 0:
        return principal / months

    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def calculate_emi(
    project_cost: float,
    financing_pct: float,
    rate_annual: float,
    tenure_months: int = 84,
    moratorium_months: int = 6,
    moratorium_type: MoratoriumType = MoratoriumType.SIMPLE_INTEREST,
    women_rebate_pct: float = 0.0,
    is_female: bool = False,
    periods_per_year: int = 12,
) -> EMIResult:
    """Calculate EMI with moratorium treatment.

    Args:
        project_cost: Total project cost in ₹
        financing_pct: Fraction financed by NSFDC (typically 0.90)
        rate_annual: Annual interest rate (e.g. 8.0 for 8%)
        tenure_months: Total loan tenure in months (default 84 = 7 years)
        moratorium_months: Moratorium period in months (default 6)
        moratorium_type: How interest is handled during moratorium
        women_rebate_pct: Rate reduction for women (e.g. 0.5 for 0.5%)
        is_female: Whether the borrower is female (triggers rebate)
        periods_per_year: Instalments per year. Must divide 12 evenly.
            Defaults to 12 (monthly) for compatibility, but every NSFDC
            scheme actually repays QUARTERLY — pass 4 for real figures.

    Returns:
        EMIResult with complete payment breakdown.

    Raises:
        ValueError: If inputs are invalid (negative cost, tenure ≤ moratorium, etc.)
    """
    if project_cost < 0:
        raise ValueError("project_cost must be non-negative")
    if tenure_months <= 0:
        raise ValueError("tenure_months must be positive")
    if moratorium_months < 0:
        raise ValueError("moratorium_months must be non-negative")
    if moratorium_months >= tenure_months:
        raise ValueError("moratorium_months must be less than tenure_months")
    if rate_annual < 0:
        raise ValueError("rate_annual must be non-negative")
    if periods_per_year <= 0 or 12 % periods_per_year != 0:
        raise ValueError(
            "periods_per_year must divide 12 evenly (1, 2, 3, 4, 6 or 12), "
            f"got {periods_per_year}"
        )

    # Integer arithmetic on purpose. `12 / periods_per_year` would make the
    # period count a float and render "over 78.0 months" in a live message.
    months_per_period = 12 // periods_per_year

    # Apply women's rebate if applicable
    effective_rate = rate_annual
    if is_female and women_rebate_pct > 0:
        effective_rate = max(0.0, rate_annual - women_rebate_pct)

    # Calculate loan amount (principal)
    principal = project_cost * financing_pct

    frequency = _FREQUENCY_LABELS.get(periods_per_year, f"{periods_per_year}x per year")

    # Handle edge case: zero principal
    if principal == 0:
        return EMIResult(
            loan_amount=0.0,
            rate_annual=round(effective_rate, 2),
            tenure_months=tenure_months,
            moratorium_months=moratorium_months,
            repayment_months=tenure_months - moratorium_months,
            moratorium_type=moratorium_type,
            moratorium_monthly_payment=0.0,
            emi_after_moratorium=0.0,
            total_payable=0.0,
            total_interest=0.0,
            periods_per_year=periods_per_year,
            instalment_frequency=frequency,
            instalment_amount=0.0,
            instalment_count=0,
            monthly_equivalent=0.0,
            moratorium_instalment=0.0,
        )

    period_rate = (effective_rate / 100) / periods_per_year
    repayment_months = tenure_months - moratorium_months

    # Instalment counts. You cannot pay a fraction of an instalment, so the
    # repayment count is an int and never below 1. The moratorium count stays a
    # float because compounding over a partial period is genuinely correct — and
    # at the monthly default both are exactly the month counts, which is what
    # keeps this byte-identical to the previous behaviour.
    repayment_periods = max(1, round(repayment_months / months_per_period))
    moratorium_periods = moratorium_months / months_per_period


    if moratorium_type == MoratoriumType.SIMPLE_INTEREST:
        # Borrower pays interest-only during moratorium; principal unchanged
        if moratorium_months > 0:
            moratorium_payment = principal * period_rate if period_rate > 0 else 0.0
        else:
            moratorium_payment = 0.0
        emi_principal = principal
        emi = _reducing_balance_emi(emi_principal, period_rate, repayment_periods)
        total_moratorium = moratorium_payment * moratorium_periods
        total_repayment = emi * repayment_periods
        total_payable = total_moratorium + total_repayment

    elif moratorium_type == MoratoriumType.CAPITALIZED:
        # No payment during moratorium; interest accrues onto principal.
        # The exponent MUST be the period count, not the month count — otherwise
        # a quarterly loan compounds three times too often.
        moratorium_payment = 0.0
        if period_rate > 0:
            emi_principal = principal * (1 + period_rate) ** moratorium_periods
        else:
            emi_principal = principal
        emi = _reducing_balance_emi(emi_principal, period_rate, repayment_periods)
        total_repayment = emi * repayment_periods
        total_payable = total_repayment  # No moratorium payments

    elif moratorium_type == MoratoriumType.SUBVENTION:
        # ₹0 during moratorium — government covers the interest
        moratorium_payment = 0.0
        emi_principal = principal  # Principal unchanged
        emi = _reducing_balance_emi(emi_principal, period_rate, repayment_periods)
        total_repayment = emi * repayment_periods
        total_payable = total_repayment  # No moratorium payments

    else:
        raise ValueError(f"Unknown moratorium type: {moratorium_type}")

    total_interest = total_payable - principal

    return EMIResult(
        loan_amount=round(principal, 2),
        rate_annual=round(effective_rate, 2),
        tenure_months=tenure_months,
        moratorium_months=moratorium_months,
        repayment_months=repayment_months,
        moratorium_type=moratorium_type,
        moratorium_monthly_payment=round(moratorium_payment, 2),
        emi_after_moratorium=round(emi, 2),
        total_payable=round(total_payable, 2),
        total_interest=round(total_interest, 2),
        periods_per_year=periods_per_year,
        instalment_frequency=frequency,
        instalment_amount=round(emi, 2),
        instalment_count=repayment_periods,
        monthly_equivalent=round(emi / months_per_period, 2),
        moratorium_instalment=round(moratorium_payment, 2),
    )
