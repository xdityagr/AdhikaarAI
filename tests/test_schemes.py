"""
Test suite for Tier 1 eligibility engine (schemes.py).

Boundary-value tests are the priority — a judge WILL test:
- Income exactly at ₹5,00,000 (MUST match)
- Income at ₹5,00,001 (MUST NOT match)
- Project cost exactly at ceiling (MUST match)
- Project cost one rupee over (MUST NOT match)

Design note: no age tests — rules.md deliberately has no age fields.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemes import UserProfile, SchemeMatch, evaluate_eligible_schemes


# ---------------------------------------------------------------------------
# UserProfile validation tests
# ---------------------------------------------------------------------------

class TestUserProfileValidation:
    """Test that UserProfile validates inputs correctly."""

    def test_valid_business_profile(self):
        p = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
            gender="male",
        )
        assert p.project_type == "business"
        assert p.category == "SC"  # default

    def test_valid_education_profile(self):
        p = UserProfile(
            project_type="education",
            project_cost=500_000,
            annual_income=200_000,
            gender="female",
        )
        assert p.project_type == "education"

    def test_project_type_normalized(self):
        """project_type should be lowercased and stripped."""
        p = UserProfile(
            project_type="  Business  ",
            project_cost=100_000,
            annual_income=300_000,
        )
        assert p.project_type == "business"

    def test_invalid_project_type_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(
                project_type="other",
                project_cost=100_000,
                annual_income=300_000,
            )

    def test_negative_cost_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(
                project_type="business",
                project_cost=-1,
                annual_income=300_000,
            )

    def test_negative_income_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(
                project_type="business",
                project_cost=100_000,
                annual_income=-1,
            )

    def test_gender_normalized(self):
        p = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
            gender="  Female  ",
        )
        assert p.gender == "female"

    def test_category_defaults_to_sc(self):
        p = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
        )
        assert p.category == "SC"


# ---------------------------------------------------------------------------
# Income boundary tests (THE critical boundary — judge will test this)
# ---------------------------------------------------------------------------

class TestIncomeBoundary:
    """Test income eligibility boundary at ₹5,00,000.

    Architecture.md: "Income ₹5,00,000 matches and ₹5,00,001 doesn't —
    this is explicitly called out as a judge test case."
    """

    def test_income_exactly_at_limit_matches(self):
        """Income == ₹5,00,000 MUST be eligible (≤, not <)."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,  # Under Micro Finance ceiling
            annual_income=500_000,
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) > 0, "Income at exactly ₹5,00,000 should match"

    def test_income_one_over_limit_no_match(self):
        """Income == ₹5,00,001 MUST NOT be eligible."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=500_001,
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) == 0, "Income at ₹5,00,001 should NOT match"

    def test_income_well_under_limit_matches(self):
        """Income well below threshold should match."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=200_000,
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) > 0

    def test_zero_income_matches(self):
        """Zero income should match — it's under the limit."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=0,
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) > 0


# ---------------------------------------------------------------------------
# Project cost boundary tests
# ---------------------------------------------------------------------------

class TestProjectCostBoundary:
    """Test project cost boundaries for each scheme."""

    def test_micro_finance_at_ceiling(self):
        """Cost exactly at ₹1,40,000 should match Micro Finance."""
        profile = UserProfile(
            project_type="business",
            project_cost=140_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = [m.scheme_id for m in matches]
        assert "MICRO_FINANCE" in scheme_ids

    def test_micro_finance_one_over(self):
        """Cost at ₹1,40,001 should NOT match Micro Finance."""
        profile = UserProfile(
            project_type="business",
            project_cost=140_001,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = [m.scheme_id for m in matches]
        assert "MICRO_FINANCE" not in scheme_ids

    def test_term_loan_at_ceiling(self):
        """Cost exactly at ₹50,00,000 should match Term Loan."""
        profile = UserProfile(
            project_type="business",
            project_cost=5_000_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = [m.scheme_id for m in matches]
        assert "TERM_LOAN" in scheme_ids

    def test_term_loan_one_over(self):
        """Cost at ₹50,00,001 should NOT match Term Loan."""
        profile = UserProfile(
            project_type="business",
            project_cost=5_000_001,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = [m.scheme_id for m in matches]
        assert "TERM_LOAN" not in scheme_ids

    def test_educational_loan_at_ceiling(self):
        """Cost at exactly ₹40,00,000 should match the Educational Loan Scheme.

        This test used to assert that ELS had NO ceiling and that ₹10 crore
        matched. That came from the PS text, which doesn't state a ceiling.
        nsfdc.nic.in/scheme does: ₹40 lakh, or 90% of course fees, whichever is
        less. The corpus now carries the real figure — see data-sources.md §3.1.
        """
        profile = UserProfile(
            project_type="education",
            project_cost=4_000_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = [m.scheme_id for m in matches]
        assert "EDUCATIONAL_LOAN" in scheme_ids, "Cost at exactly ₹40L should match"

    def test_educational_loan_one_over(self):
        """Cost at ₹40,00,001 should NOT match the Educational Loan Scheme."""
        profile = UserProfile(
            project_type="education",
            project_cost=4_000_001,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = [m.scheme_id for m in matches]
        assert "EDUCATIONAL_LOAN" not in scheme_ids


# ---------------------------------------------------------------------------
# Project type routing tests
# ---------------------------------------------------------------------------

class TestProjectTypeRouting:
    """Test that project type correctly routes to scheme candidates."""

    def test_small_business_gets_micro_finance_not_term_loan(self):
        """A ₹1 lakh project is below Term Loan's ₹1.40 lakh floor.

        This test previously asserted that ₹1 lakh matched Term Loan too. It
        doesn't: nsfdc.nic.in/scheme puts Term Loan at ₹1.40 lakh to ₹50 lakh,
        so small projects belong to the micro-finance products. That floor is
        what produces the demo's Why-Not line.
        """
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = {m.scheme_id for m in matches}
        assert "MICRO_FINANCE" in scheme_ids
        assert "AAJEEVIKA_MICRO_FINANCE" in scheme_ids
        assert "TERM_LOAN" not in scheme_ids, "₹1L is below Term Loan's ₹1.40L floor"
        assert "EDUCATIONAL_LOAN" not in scheme_ids

    def test_larger_business_gets_term_loan_not_micro_finance(self):
        """A ₹2 lakh project clears Term Loan's floor and exceeds the micro ceiling."""
        profile = UserProfile(
            project_type="business",
            project_cost=200_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = {m.scheme_id for m in matches}
        assert "TERM_LOAN" in scheme_ids
        assert "UDYAM_NIDHI" in scheme_ids
        assert "MICRO_FINANCE" not in scheme_ids, "₹2L is over the ₹1.40L micro ceiling"

    def test_education_gets_educational_loan_only(self):
        """Education project should only match Educational Loan."""
        profile = UserProfile(
            project_type="education",
            project_cost=500_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = {m.scheme_id for m in matches}
        assert "EDUCATIONAL_LOAN" in scheme_ids
        assert "MICRO_FINANCE" not in scheme_ids
        assert "TERM_LOAN" not in scheme_ids

    def test_business_over_micro_finance_still_gets_term_loan(self):
        """Business cost over ₹1.4L should drop Micro Finance but keep Term Loan."""
        profile = UserProfile(
            project_type="business",
            project_cost=200_000,  # Over Micro Finance, under Term Loan
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        scheme_ids = {m.scheme_id for m in matches}
        assert "MICRO_FINANCE" not in scheme_ids
        assert "TERM_LOAN" in scheme_ids


# ---------------------------------------------------------------------------
# Category check tests
# ---------------------------------------------------------------------------

class TestCategoryCheck:
    """Test that category filtering works (PS targets SC beneficiaries)."""

    def test_sc_category_matches(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
            category="SC",
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) > 0

    def test_non_sc_category_no_match(self):
        """Non-SC category should return no matches."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
            category="GENERAL",
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# Women's rebate tests
# ---------------------------------------------------------------------------

class TestWomensRebate:
    """Test that women's rebate is flagged in the match result."""

    def test_female_education_gets_rebate_flag(self):
        """Female education applicant should get women_rebate_pct > 0."""
        profile = UserProfile(
            project_type="education",
            project_cost=500_000,
            annual_income=300_000,
            gender="female",
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) == 1
        assert matches[0].women_rebate_pct == 0.5
        assert "rebate" in matches[0].why_eligible.lower()

    def test_male_education_no_rebate_mention(self):
        """Male education applicant should NOT have rebate in explanation."""
        profile = UserProfile(
            project_type="education",
            project_cost=500_000,
            annual_income=300_000,
            gender="male",
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) == 1
        assert "rebate" not in matches[0].why_eligible.lower()


# ---------------------------------------------------------------------------
# SchemeMatch structure tests
# ---------------------------------------------------------------------------

class TestSchemeMatchOutput:
    """Test that the match result contains all expected fields."""

    def test_match_has_required_fields(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=300_000,
        )
        matches = evaluate_eligible_schemes(profile)
        assert len(matches) >= 1
        m = matches[0]
        assert m.scheme_id
        assert m.name
        assert m.why_eligible
        assert m.rate_min > 0
        assert m.rate_max >= m.rate_min
        assert m.financing_pct > 0

    def test_no_match_returns_empty_list(self):
        """When nothing matches, return an empty list (not None, not error)."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=1_000_000,  # Way over income limit
        )
        matches = evaluate_eligible_schemes(profile)
        assert matches == []
