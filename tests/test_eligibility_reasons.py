"""
Why / Why-Not trail tests.

Explaining why a scheme did NOT match is one of the PS's two stated impact goals
("enhance financial literacy"), and it is the 1:10 beat of the demo script.

Assertions target the machine-readable `rule` tag rather than the prose, so that
rewording the copy before the demo doesn't break the suite. Where a test does
check the sentence, it checks for a figure that must appear, not phrasing.
"""

from __future__ import annotations

from src.schemes import (
    EligibilityResult,
    UserProfile,
    evaluate_eligibility,
    evaluate_eligible_schemes,
    notable_rejections,
)


# ---------------------------------------------------------------------------
# Rejection reasons — the load-bearing half of the trail
# ---------------------------------------------------------------------------

class TestRejectionReasons:
    """Every non-match must carry a rule tag and a user-facing sentence."""

    def test_cost_floor_rejection_names_the_floor(self):
        """THE demo beat: '₹1.2 lakh is below Term Loan's ₹1.40 lakh floor'."""
        profile = UserProfile(
            project_type="business",
            project_cost=120_000,
            annual_income=280_000,
        )
        result = evaluate_eligibility(profile)
        term_loan = [r for r in result.rejections if r.scheme_id == "TERM_LOAN"]
        assert len(term_loan) == 1, "Term Loan should be rejected with a reason"
        assert term_loan[0].rule == "COST_FLOOR"
        assert "1,40,000" in term_loan[0].reason

    def test_cost_ceiling_rejection_names_the_ceiling(self):
        profile = UserProfile(
            project_type="business",
            project_cost=200_000,
            annual_income=280_000,
        )
        result = evaluate_eligibility(profile)
        micro = [r for r in result.rejections if r.scheme_id == "MICRO_FINANCE"]
        assert len(micro) == 1
        assert micro[0].rule == "COST_CEILING"

    def test_income_rejection_names_the_limit(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=600_000,
        )
        result = evaluate_eligibility(profile)
        assert result.matches == []
        income_rejections = [r for r in result.rejections if r.rule == "INCOME"]
        assert income_rejections, "Over-income must produce INCOME rejections"
        # Indian digit grouping — 5,00,000 not 500,000. See schemes.format_rupees.
        assert "5,00,000" in income_rejections[0].reason

    def test_every_scheme_is_accounted_for(self):
        """A scheme is either a match or a rejection — never silently dropped."""
        profile = UserProfile(
            project_type="business",
            project_cost=120_000,
            annual_income=280_000,
        )
        result = evaluate_eligibility(profile)
        seen = {m.scheme_id for m in result.matches} | {r.scheme_id for r in result.rejections}
        assert len(seen) == 5


# ---------------------------------------------------------------------------
# No Dead Ends — an out-of-category user gets a referral, not a wall
# ---------------------------------------------------------------------------

class TestNoDeadEnds:
    """A judge WILL test an out-of-category profile."""

    def test_sc_applicant_has_no_category_note(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=280_000,
            category="SC",
        )
        assert evaluate_eligibility(profile).category_note == ""

    def test_obc_applicant_referred_to_nbcfdc(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=280_000,
            category="OBC",
        )
        result = evaluate_eligibility(profile)
        assert result.matches == []
        assert "NBCFDC" in result.category_note

    def test_st_applicant_referred_to_nstfdc(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=280_000,
            category="ST",
        )
        assert "NSTFDC" in evaluate_eligibility(profile).category_note

    def test_unknown_category_still_gets_a_route(self):
        """Never a bare rejection, even for a category we don't map."""
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=280_000,
            category="GENERAL",
        )
        note = evaluate_eligibility(profile).category_note
        assert note, "An unmapped category must still get a referral note"


# ---------------------------------------------------------------------------
# notable_rejections — what actually reaches the user
# ---------------------------------------------------------------------------

class TestNotableRejections:
    """Show thresholds the user missed; drop noise they already know."""

    def test_project_type_rejections_are_dropped(self):
        """Someone asking for a business loan needn't be told ELS is for education."""
        profile = UserProfile(
            project_type="business",
            project_cost=120_000,
            annual_income=280_000,
        )
        result = evaluate_eligibility(profile)
        assert any(r.rule == "PROJECT_TYPE" for r in result.rejections)
        assert all(r.rule != "PROJECT_TYPE" for r in notable_rejections(result))

    def test_cost_floor_is_ranked_first(self):
        profile = UserProfile(
            project_type="business",
            project_cost=120_000,
            annual_income=280_000,
        )
        notable = notable_rejections(evaluate_eligibility(profile))
        assert notable, "There should be something worth telling this user"
        assert notable[0].rule == "COST_FLOOR"

    def test_limit_is_respected(self):
        profile = UserProfile(
            project_type="business",
            project_cost=600_000,
            annual_income=280_000,
        )
        assert len(notable_rejections(evaluate_eligibility(profile), limit=1)) <= 1


# ---------------------------------------------------------------------------
# Backwards compatibility — the wrapper protects existing consumers
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """cache.generate_fingerprint, llm.py and graph.py all consume the old shape."""

    def test_wrapper_returns_the_same_matches(self):
        for cost in (100_000, 120_000, 200_000, 600_000):
            profile = UserProfile(
                project_type="business",
                project_cost=cost,
                annual_income=280_000,
            )
            assert evaluate_eligible_schemes(profile) == evaluate_eligibility(profile).matches

    def test_wrapper_returns_empty_for_non_sc(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=280_000,
            category="OBC",
        )
        assert evaluate_eligible_schemes(profile) == []


# ---------------------------------------------------------------------------
# education_status — PS-mandated intake field
# ---------------------------------------------------------------------------

class TestEducationStatus:
    """The PS names education status as an intake input.

    It deliberately does NOT gate eligibility: no published NSFDC rule keys
    eligibility on it, and inventing one would repeat the unverified-age mistake.
    It earns its place through delivery adaptation and Train-then-Credit routing.
    """

    def test_defaults_to_unknown(self):
        profile = UserProfile(
            project_type="business",
            project_cost=100_000,
            annual_income=280_000,
        )
        assert profile.education_status == "unknown"

    def test_does_not_change_eligibility(self):
        results = []
        for status in ("below_10th", "10th_to_12th", "graduate_plus", "unknown"):
            profile = UserProfile(
                project_type="business",
                project_cost=100_000,
                annual_income=280_000,
                education_status=status,
            )
            results.append({m.scheme_id for m in evaluate_eligible_schemes(profile)})
        assert all(r == results[0] for r in results), "education_status must not gate eligibility"
