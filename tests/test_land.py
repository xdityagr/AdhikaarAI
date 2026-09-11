"""
Land extraction tests.

Every string here is a real sentence from the corpus, not one invented to pass.
That matters for an extractor: prose written by fifty different state departments
does things no hand-written example would think of, and each of the cases below
is one the first version of this module got wrong.

The governing bias is precision over recall. A land ceiling decides whether
someone is told they qualify, so a figure we are not sure of must become
"check this yourself" and never a number.
"""

from __future__ import annotations

import pytest

from src.corpus.land import extract


HECTARE = 2.47105


class TestCeilings:
    def test_up_to_hectares(self):
        rule = extract("1. The applicant should have a land holding of up to 2 hectares")
        assert rule.max_acres == pytest.approx(2 * HECTARE)
        assert rule.min_acres is None

    def test_less_than_acres(self):
        rule = extract("1. The applicant family has less than 5 acres of land")
        assert rule.max_acres == pytest.approx(5.0)

    def test_maximum_prefix(self):
        rule = extract("Beneficiary should own a maximum of 2.5 Acre Nehri Land")
        assert rule.max_acres == pytest.approx(2.5)

    def test_parenthesised_figure(self):
        rule = extract("The applicant must own cultivable land (up to 2 acres)")
        assert rule.max_acres == pytest.approx(2.0)


class TestMinimumsAreNotCeilings:
    """Reading "at least" as a cap inverts who qualifies, and most of the land
    sentences in the corpus are minimums."""

    def test_at_least_is_a_minimum(self):
        rule = extract("The applicant should possess owned or leased land of at "
                       "least 0.2 hectares or more")
        assert rule.min_acres == pytest.approx(0.2 * HECTARE)
        assert rule.max_acres is None

    def test_minimum_of_acres(self):
        rule = extract("The applicant should hold a minimum of 1.5 acres of land "
                       "under the command area of the tubewell")
        assert rule.min_acres == pytest.approx(1.5)
        assert rule.max_acres is None


class TestThingsThatAreNotSomeonesField:
    """A number in hectares is not automatically the applicant's holding."""

    def test_water_spread_area_is_not_a_holding(self):
        rule = extract("- The applicant should be a farmer having a water spread "
                       "area of 2 hectares or less")
        assert rule.max_acres is None

    def test_a_subsidy_cap_is_not_an_eligibility_ceiling(self):
        """"The maximum land area allowed under the scheme is 2 hectares" caps
        the grant, not the applicant. A farmer with five acres still qualifies,
        for two of them — so reading it as a ceiling excludes the very people it
        was written to pay."""
        rule = extract("The maximum land area allowed under the scheme is 2 hectares")
        assert rule.max_acres is None

    def test_a_definition_is_not_this_schemes_rule(self):
        rule = extract("(Note: A small farmer is one who owns up to 5 acres of "
                       "unirrigated land.)")
        assert rule.max_acres is None

    def test_a_cue_belonging_to_something_else_does_not_flip_direction(self):
        """The sentence that broke the first version: "An area of more than 5
        acres with comfortable accommodation of not more than 9 lettable rooms".
        The max cue is about the rooms."""
        rule = extract("An area of more than 5 acres with comfortable "
                       "accommodation of not more than 9 lettable rooms")
        assert rule.max_acres is None


class TestConditionalRulesAreFlaggedNotGuessed:
    def test_two_ceilings_in_one_sentence_are_not_resolved(self):
        """"up to 5 acres of unirrigated land or up to 1.25 acres of irrigated"
        cannot be reduced to one number without knowing which land they have.
        Picking the smaller would exclude a farmer with three unirrigated acres
        who plainly qualifies."""
        rule = extract("The applicant should own up to 5 acres of unirrigated "
                       "land or up to 2 acres of irrigated land")
        assert rule.max_acres is None
        assert rule.unquantified is True

    def test_alternatives_on_separate_lines_are_flagged(self):
        """Punjab's old-age pension, verbatim. The alternatives are separate
        list items, so checking within one sentence missed it — and taking the
        smallest would deny the pension to a man with four acres of Barani land
        who is entitled to it."""
        rule = extract(
            "1. Beneficiary should own any of the below mentioned amount of land :-\n"
            "   1. Maximum 2.5 Acre Nehri or Chahi Land, OR\n"
            "   1. Maximum 5 Acre Barani Land, OR\n"
            "   1. Waterlogged 5 Acre Land.\n"
        )
        assert rule.max_acres is None
        assert rule.unquantified is True

    def test_a_local_unit_is_recorded_but_never_converted(self):
        """A bigha runs from about a quarter-acre to over one and a half
        depending on the district. Converting it would invent precision."""
        rule = extract("The applicant should own agricultural land of at least 3 bighas")
        assert rule.min_acres is None
        assert rule.max_acres is None
        assert rule.unquantified is True
        assert rule.evidence


class TestLandless:
    def test_a_requirement_is_read(self):
        assert extract("The family of the applicant should be landless").landless_required
        assert extract("The applicant must be landless and houseless").landless_required

    def test_being_listed_as_eligible_is_not_a_requirement(self):
        """The failure that would have hurt most. "Farmers belonging to all
        categories like general/SC/ST/BPL/Women and Landless persons are
        eligible" is the scheme opening its doors wider — reading it as a rule
        would exclude every landowner it was inviting."""
        rule = extract("Farmers belonging to all categories like general/SC/ST/"
                       "BPL/Women and Landless persons of Himachal Pradesh are eligible")
        assert rule.landless_required is False

    def test_landless_as_a_named_group_is_not_a_requirement(self):
        rule = extract("Applicants belonging to a Scheduled Caste, Denotified "
                       "Nomadic Tribe, Landless Agricultural Labourer, or a "
                       "Traditional Artisan may apply")
        assert rule.landless_required is False


class TestEvidence:
    def test_every_finding_carries_its_sentence(self):
        rule = extract("1. The applicant should have a land holding of up to 2 hectares")
        assert rule.evidence
        assert "2 hectares" in rule.evidence[0]

    def test_a_decimal_point_does_not_split_the_sentence(self):
        """`.` is both a full stop and a decimal separator. Splitting on every
        one truncated the evidence and, worse, hid the beginning of a sentence
        from the checks that read it — which is how a definition slipped past
        the definition filter."""
        rule = extract("The applicant must have agricultural land of at least "
                       "0.25 acres to qualify")
        assert rule.min_acres == pytest.approx(0.25)
        assert rule.evidence[0].startswith("The applicant")

    def test_nothing_found_is_empty_not_false(self):
        rule = extract("The applicant should be a resident of the state.")
        assert rule.empty
        assert rule.max_acres is None and rule.min_acres is None

    def test_no_prose_at_all(self):
        assert extract(None).empty
        assert extract("").empty
