"""
Test suite for EMI Calculator (calculator.py).

Tests cover:
1. Standard reducing-balance EMI correctness (cross-checked against formula)
2. All three moratorium treatments: simple interest, capitalized, subvention
3. Women's rebate application
4. Edge cases: zero cost, zero rate, input validation
5. Financial invariants (total_payable > principal, etc.)

The EMI formula is: P × r × (1+r)^n / ((1+r)^n - 1)
where P = principal, r = monthly rate, n = repayment months.
"""

from __future__ import annotations

import pytest

from src.calculator import calculate_emi, MoratoriumType, EMIResult


# ---------------------------------------------------------------------------
# Basic EMI correctness
# ---------------------------------------------------------------------------

class TestBasicEMI:
    """Test standard EMI calculation (simple interest moratorium)."""

    def test_basic_micro_finance_emi(self):
        """₹1,40,000 project, 90% financed, 6.5%, 84 months, 6-month moratorium."""
        result = calculate_emi(
            project_cost=140_000,
            financing_pct=0.90,
            rate_annual=6.5,
            tenure_months=84,
            moratorium_months=6,
        )
        # Principal = 140000 * 0.90 = 126000
        assert result.loan_amount == 126_000.0
        assert result.rate_annual == 6.5
        assert result.tenure_months == 84
        assert result.moratorium_months == 6
        assert result.repayment_months == 78
        # EMI should be around ₹1,850-1,950 for this scenario
        assert 1800 < result.emi_after_moratorium < 2000
        # Moratorium payment = 126000 * (6.5/100/12) ≈ ₹682.50
        assert 680 < result.moratorium_monthly_payment < 685
        # Total should exceed principal
        assert result.total_payable > result.loan_amount

    def test_basic_term_loan_emi(self):
        """₹50,00,000 project, 90% financed, 8%, 84 months, 6-month moratorium."""
        result = calculate_emi(
            project_cost=5_000_000,
            financing_pct=0.90,
            rate_annual=8.0,
            tenure_months=84,
            moratorium_months=6,
        )
        assert result.loan_amount == 4_500_000.0
        assert result.repayment_months == 78
        # EMI should be significant for ₹45L loan
        assert result.emi_after_moratorium > 50_000
        assert result.total_payable > result.loan_amount

    def test_educational_loan_basic(self):
        """Education loan with women's rebate."""
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=6.5,
            tenure_months=84,
            moratorium_months=6,
            women_rebate_pct=0.5,
            is_female=True,
        )
        # Rate should be 6.5 - 0.5 = 6.0
        assert result.rate_annual == 6.0
        assert result.loan_amount == 450_000.0


# ---------------------------------------------------------------------------
# Moratorium treatment tests
# ---------------------------------------------------------------------------

class TestMoratoriumTypes:
    """Test all three moratorium treatments produce different results."""

    @pytest.fixture
    def base_params(self):
        return {
            "project_cost": 500_000,
            "financing_pct": 0.90,
            "rate_annual": 8.0,
            "tenure_months": 84,
            "moratorium_months": 6,
        }

    def test_simple_interest_moratorium(self, base_params):
        """Borrower pays interest-only during moratorium."""
        result = calculate_emi(**base_params, moratorium_type=MoratoriumType.SIMPLE_INTEREST)
        # Should have non-zero moratorium payment
        assert result.moratorium_monthly_payment > 0
        # Principal unchanged for EMI calculation
        assert result.moratorium_type == MoratoriumType.SIMPLE_INTEREST

    def test_capitalized_moratorium(self, base_params):
        """No payment during moratorium; interest accrues onto principal."""
        result = calculate_emi(**base_params, moratorium_type=MoratoriumType.CAPITALIZED)
        # Zero moratorium payment
        assert result.moratorium_monthly_payment == 0.0
        # Higher EMI because interest got added to principal
        simple_result = calculate_emi(**base_params, moratorium_type=MoratoriumType.SIMPLE_INTEREST)
        assert result.emi_after_moratorium > simple_result.emi_after_moratorium

    def test_subvention_moratorium(self, base_params):
        """Government covers interest during moratorium (₹0)."""
        result = calculate_emi(**base_params, moratorium_type=MoratoriumType.SUBVENTION)
        # Zero moratorium payment
        assert result.moratorium_monthly_payment == 0.0
        # Same EMI as simple interest (principal unchanged)
        simple_result = calculate_emi(**base_params, moratorium_type=MoratoriumType.SIMPLE_INTEREST)
        assert result.emi_after_moratorium == simple_result.emi_after_moratorium
        # But lower total payable (no moratorium payments)
        assert result.total_payable < simple_result.total_payable

    def test_capitalized_higher_total_than_simple(self, base_params):
        """Capitalized moratorium should cost more overall than simple interest."""
        simple = calculate_emi(**base_params, moratorium_type=MoratoriumType.SIMPLE_INTEREST)
        capitalized = calculate_emi(**base_params, moratorium_type=MoratoriumType.CAPITALIZED)
        assert capitalized.total_payable > simple.total_payable

    def test_subvention_lowest_total(self, base_params):
        """Subvention should have the lowest total payable."""
        simple = calculate_emi(**base_params, moratorium_type=MoratoriumType.SIMPLE_INTEREST)
        subvention = calculate_emi(**base_params, moratorium_type=MoratoriumType.SUBVENTION)
        assert subvention.total_payable < simple.total_payable


# ---------------------------------------------------------------------------
# Women's rebate tests
# ---------------------------------------------------------------------------

class TestWomensRebate:
    """Test the 0.5% rate reduction for female borrowers."""

    def test_rebate_reduces_rate(self):
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=6.5,
            women_rebate_pct=0.5,
            is_female=True,
        )
        assert result.rate_annual == 6.0

    def test_no_rebate_for_male(self):
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=6.5,
            women_rebate_pct=0.5,
            is_female=False,
        )
        assert result.rate_annual == 6.5

    def test_rebate_lowers_emi(self):
        male_result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=6.5,
            women_rebate_pct=0.5,
            is_female=False,
        )
        female_result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=6.5,
            women_rebate_pct=0.5,
            is_female=True,
        )
        assert female_result.emi_after_moratorium < male_result.emi_after_moratorium

    def test_rebate_does_not_go_below_zero(self):
        """If rate < rebate, rate should floor at 0."""
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=0.3,
            women_rebate_pct=0.5,
            is_female=True,
        )
        assert result.rate_annual == 0.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and input validation."""

    def test_zero_project_cost(self):
        """Zero cost → zero everything."""
        result = calculate_emi(
            project_cost=0,
            financing_pct=0.90,
            rate_annual=8.0,
        )
        assert result.loan_amount == 0.0
        assert result.emi_after_moratorium == 0.0
        assert result.total_payable == 0.0
        assert result.total_interest == 0.0

    def test_zero_rate(self):
        """Zero rate → principal / months."""
        result = calculate_emi(
            project_cost=120_000,
            financing_pct=1.0,
            rate_annual=0.0,
            tenure_months=12,
            moratorium_months=0,
        )
        # Should be simple division: 120000 / 12 = 10000
        assert result.emi_after_moratorium == 10_000.0
        assert result.moratorium_monthly_payment == 0.0

    def test_zero_moratorium(self):
        """No moratorium → all months are repayment."""
        result = calculate_emi(
            project_cost=100_000,
            financing_pct=0.90,
            rate_annual=8.0,
            tenure_months=84,
            moratorium_months=0,
        )
        assert result.repayment_months == 84
        assert result.moratorium_months == 0
        assert result.moratorium_monthly_payment == 0.0

    def test_negative_cost_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_emi(project_cost=-1, financing_pct=0.90, rate_annual=8.0)

    def test_zero_tenure_raises(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_emi(project_cost=100_000, financing_pct=0.90, rate_annual=8.0, tenure_months=0)

    def test_moratorium_exceeds_tenure_raises(self):
        with pytest.raises(ValueError, match="less than tenure"):
            calculate_emi(
                project_cost=100_000,
                financing_pct=0.90,
                rate_annual=8.0,
                tenure_months=12,
                moratorium_months=12,
            )

    def test_negative_rate_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_emi(project_cost=100_000, financing_pct=0.90, rate_annual=-1)


# ---------------------------------------------------------------------------
# Financial invariant tests
# ---------------------------------------------------------------------------

class TestFinancialInvariants:
    """Test that financial invariants always hold."""

    def test_total_payable_exceeds_principal(self):
        """With positive rate, you always pay more than you borrowed."""
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=8.0,
            tenure_months=84,
            moratorium_months=6,
        )
        assert result.total_payable > result.loan_amount

    def test_total_interest_positive(self):
        """With positive rate, total interest > 0."""
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=8.0,
        )
        assert result.total_interest > 0

    def test_total_interest_zero_rate(self):
        """Zero rate means zero interest."""
        result = calculate_emi(
            project_cost=500_000,
            financing_pct=0.90,
            rate_annual=0.0,
            moratorium_months=0,
        )
        assert result.total_interest == 0.0

    def test_result_fields_are_rounded(self):
        """All monetary fields should be rounded to 2 decimal places."""
        result = calculate_emi(
            project_cost=333_333,
            financing_pct=0.90,
            rate_annual=7.77,
        )
        assert result.loan_amount == round(result.loan_amount, 2)
        assert result.emi_after_moratorium == round(result.emi_after_moratorium, 2)
        assert result.moratorium_monthly_payment == round(result.moratorium_monthly_payment, 2)
        assert result.total_payable == round(result.total_payable, 2)
        assert result.total_interest == round(result.total_interest, 2)


# ---------------------------------------------------------------------------
# Instalment frequency — NSFDC repays QUARTERLY, not monthly
# ---------------------------------------------------------------------------

class TestInstalmentFrequency:
    """The calculator defaulted to monthly EMIs, but every NSFDC scheme repays
    quarterly (Udyam Nidhi quarterly or half-yearly). A monthly figure is not a
    number the borrower is ever actually asked to pay.

    periods_per_year defaults to 12 specifically so every test above this line
    keeps passing byte-identically.
    """

    def test_default_is_monthly_and_unchanged(self):
        """Passing periods_per_year=12 explicitly must equal the old behaviour."""
        implicit = calculate_emi(
            project_cost=140_000, financing_pct=0.90, rate_annual=6.5,
            tenure_months=84, moratorium_months=6,
        )
        explicit = calculate_emi(
            project_cost=140_000, financing_pct=0.90, rate_annual=6.5,
            tenure_months=84, moratorium_months=6, periods_per_year=12,
        )
        assert implicit == explicit
        assert implicit.instalment_frequency == "monthly"

    def test_quarterly_instalment_count(self):
        """84-month tenure, 6-month moratorium -> 78 months -> 26 quarters."""
        result = calculate_emi(
            project_cost=500_000, financing_pct=0.90, rate_annual=8.0,
            tenure_months=84, moratorium_months=6, periods_per_year=4,
        )
        assert result.instalment_count == 26
        assert result.instalment_frequency == "quarterly"
        assert result.repayment_months == 78

    def test_repayment_months_stays_an_integer(self):
        """A float here renders as 'over 78.0 months' in a live message."""
        result = calculate_emi(
            project_cost=500_000, financing_pct=0.90, rate_annual=8.0,
            tenure_months=84, moratorium_months=6, periods_per_year=4,
        )
        assert isinstance(result.repayment_months, int)
        assert isinstance(result.instalment_count, int)

    def test_quarterly_instalment_is_about_three_monthly_payments(self):
        params = {
            "project_cost": 500_000, "financing_pct": 0.90, "rate_annual": 8.0,
            "tenure_months": 84, "moratorium_months": 6,
        }
        monthly = calculate_emi(**params, periods_per_year=12)
        quarterly = calculate_emi(**params, periods_per_year=4)
        ratio = quarterly.instalment_amount / monthly.instalment_amount
        assert 2.9 < ratio < 3.1

    def test_monthly_equivalent_divides_the_instalment(self):
        result = calculate_emi(
            project_cost=500_000, financing_pct=0.90, rate_annual=8.0,
            tenure_months=84, moratorium_months=6, periods_per_year=4,
        )
        assert abs(result.monthly_equivalent - result.instalment_amount / 3) < 0.01

    def test_capitalized_quarterly_costs_more_than_simple_quarterly(self):
        """The compounding exponent must be the PERIOD count, not the month count."""
        params = {
            "project_cost": 500_000, "financing_pct": 0.90, "rate_annual": 8.0,
            "tenure_months": 84, "moratorium_months": 6, "periods_per_year": 4,
        }
        capitalized = calculate_emi(**params, moratorium_type=MoratoriumType.CAPITALIZED)
        simple = calculate_emi(**params, moratorium_type=MoratoriumType.SIMPLE_INTEREST)
        assert capitalized.instalment_amount > simple.instalment_amount

    def test_half_yearly_is_supported(self):
        """Udyam Nidhi is published as quarterly OR half-yearly."""
        result = calculate_emi(
            project_cost=500_000, financing_pct=0.90, rate_annual=13.0,
            tenure_months=60, moratorium_months=3, periods_per_year=2,
        )
        assert result.instalment_frequency == "half-yearly"

    def test_periods_must_divide_twelve_evenly(self):
        with pytest.raises(ValueError, match="divide 12"):
            calculate_emi(
                project_cost=100_000, financing_pct=0.90, rate_annual=8.0,
                tenure_months=84, moratorium_months=6, periods_per_year=5,
            )
