"""
Financial literacy tests.

These render the numbers a person will make a borrowing decision on, so the
tests check the arithmetic and the disclosures, not the phrasing.
"""

from __future__ import annotations

import pytest

from src.calculator import MoratoriumType, calculate_emi
from src.config import SCHEMES, get_settings
from src.literacy import (
    format_fraud_shield,
    format_scheme_comparison,
    format_instalment,
    format_moneylender_comparison,
    format_moratorium_strip,
    format_priority_note,
    format_true_cost,
    format_why_not,
)
from src.schemes import UserProfile, evaluate_eligibility, format_rupees


def _micro_finance_emi(project_cost: float = 120_000):
    """Sunita's profile from the demo script: a ₹1.2L tailoring unit."""
    s = SCHEMES["MICRO_FINANCE"]
    return calculate_emi(
        project_cost=project_cost,
        financing_pct=s["financing_pct"],
        rate_annual=s["rate_min"],
        tenure_months=s["tenure_months"],
        moratorium_months=s["moratorium_months"],
        periods_per_year=s["periods_per_year"],
    )


# ---------------------------------------------------------------------------
# Rupee formatting — Indian grouping
# ---------------------------------------------------------------------------

class TestRupeeFormatting:
    """12,34,567 — not 1,234,567. Every user-facing figure goes through this."""

    def test_lakh_grouping(self):
        assert format_rupees(120_000) == "₹1,20,000"
        assert format_rupees(500_000) == "₹5,00,000"

    def test_crore_grouping(self):
        assert format_rupees(50_000_000) == "₹5,00,00,000"

    def test_small_amounts_unchanged(self):
        assert format_rupees(999) == "₹999"

    def test_rounds_to_whole_rupees(self):
        assert format_rupees(1234.67) == "₹1,235"


# ---------------------------------------------------------------------------
# True Cost — the total, not the instalment
# ---------------------------------------------------------------------------

class TestTrueCost:
    def test_shows_all_three_figures(self):
        emi = _micro_finance_emi()
        out = format_true_cost(emi)
        assert format_rupees(emi.loan_amount) in out
        assert format_rupees(emi.total_payable) in out
        assert format_rupees(emi.total_interest) in out

    def test_total_exceeds_principal(self):
        emi = _micro_finance_emi()
        assert emi.total_payable > emi.loan_amount
        assert emi.total_interest > 0


# ---------------------------------------------------------------------------
# Moneylender comparison — the highest-impact message in the product
# ---------------------------------------------------------------------------

class TestMoneylenderComparison:
    def test_informal_cost_far_exceeds_scheme_cost(self):
        """A concessional loan is only meaningful next to the real alternative."""
        emi = _micro_finance_emi()
        out = format_moneylender_comparison(emi, monthly_rate_pct=5.0)
        informal = emi.loan_amount * 0.05 * emi.repayment_months
        assert informal > emi.total_interest * 5, "5%/month should dwarf 6.5%/year"
        assert format_rupees(informal) in out

    def test_states_its_assumption(self):
        """Challenged on the number, we must have a stated model, not a shrug."""
        out = format_moneylender_comparison(_micro_finance_emi(), monthly_rate_pct=5.0)
        assert "principal repaid at the end" in out

    def test_rate_comes_from_config_not_a_literal(self):
        """Changing the setting must change the output."""
        emi = _micro_finance_emi()
        settings = get_settings()
        settings.moneylender_monthly_rate_pct = 3.0
        at_three = format_moneylender_comparison(emi)
        settings.moneylender_monthly_rate_pct = 8.0
        at_eight = format_moneylender_comparison(emi)
        assert at_three != at_eight
        assert "3% a month" in at_three
        assert "8% a month" in at_eight


# ---------------------------------------------------------------------------
# Instalment and moratorium presentation
# ---------------------------------------------------------------------------

class TestInstalmentPresentation:
    def test_quarterly_is_named_as_quarterly(self):
        """NSFDC repays quarterly — the message must not say 'monthly'."""
        out = format_instalment(_micro_finance_emi())
        assert "Quarterly" in out

    def test_shows_a_monthly_figure_to_budget_against(self):
        emi = _micro_finance_emi()
        assert format_rupees(emi.monthly_equivalent) in format_instalment(emi)

    def test_moratorium_strip_warns_interest_still_accrues(self):
        out = format_moratorium_strip(_micro_finance_emi())
        assert "not free" in out

    def test_moratorium_strip_empty_when_no_moratorium(self):
        s = SCHEMES["MICRO_FINANCE"]
        emi = calculate_emi(
            project_cost=120_000,
            financing_pct=s["financing_pct"],
            rate_annual=s["rate_min"],
            tenure_months=36,
            moratorium_months=0,
            periods_per_year=4,
        )
        assert format_moratorium_strip(emi) == ""


# ---------------------------------------------------------------------------
# Why-Not and disclosures
# ---------------------------------------------------------------------------

class TestWhyNot:
    def test_names_the_threshold_that_was_missed(self):
        result = evaluate_eligibility(UserProfile(
            project_type="business", project_cost=120_000, annual_income=280_000,
        ))
        assert "1,40,000" in format_why_not(result)

    def test_empty_when_nothing_informative_to_say(self):
        """Education applicants get only PROJECT_TYPE rejections, which are noise."""
        result = evaluate_eligibility(UserProfile(
            project_type="education", project_cost=500_000, annual_income=280_000,
        ))
        assert format_why_not(result) == ""


class TestDisclosures:
    def test_fraud_shield_states_the_government_charges_nothing(self):
        out = format_fraud_shield()
        assert "never charges a fee" in out
        assert "free" in out

    def test_priority_note_only_for_women_on_priority_schemes(self):
        priority = {"women": 0.40}
        assert "40%" in format_priority_note(priority, "female")
        assert format_priority_note(priority, "male") == ""
        assert format_priority_note(None, "female") == ""


# ---------------------------------------------------------------------------
# Scheme comparison — same project, different scheme, different price
# ---------------------------------------------------------------------------

class TestSchemeComparison:
    """A ₹1.2L project qualifies for MFS at 6.5% AND Aajeevika at 15%.

    Both published by NSFDC, 8.5 points apart, for the same money. Being routed
    to the wrong one of two schemes you equally qualify for is a pure, invisible
    loss — and this is the feature that makes it visible.
    """

    def _priced(self, project_cost: float):
        from src.calculator import calculate_emi
        result = evaluate_eligibility(UserProfile(
            project_type="business", project_cost=project_cost, annual_income=280_000,
        ))
        priced = []
        for match in result.matches:
            s = SCHEMES[match.scheme_id]
            priced.append((match, calculate_emi(
                project_cost=project_cost, financing_pct=s["financing_pct"],
                rate_annual=match.rate_min, tenure_months=s["tenure_months"],
                moratorium_months=s["moratorium_months"],
                periods_per_year=s["periods_per_year"],
            )))
        return priced

    def test_cheapest_scheme_is_named_first(self):
        out = format_scheme_comparison(self._priced(120_000))
        assert "Micro Finance Scheme" in out
        assert "cheapest" in out

    def test_quantifies_the_difference(self):
        priced = self._priced(120_000)
        out = format_scheme_comparison(priced)
        costs = sorted(emi.total_interest for _, emi in priced)
        assert format_rupees(costs[-1] - costs[0]) in out

    def test_silent_when_only_one_scheme_matches(self):
        """Never manufacture a comparison out of a single option."""
        result = evaluate_eligibility(UserProfile(
            project_type="education", project_cost=500_000, annual_income=280_000,
        ))
        assert len(result.matches) == 1
        assert format_scheme_comparison([]) == ""
