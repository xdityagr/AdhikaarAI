"""
Owning things, read out of prose.

The sibling of the land extraction, and the half of Phase 3 that was missing —
`land.py`'s docstring mentions assets, which made the job look finished when
only land had been done.

Almost every case below is a real sentence from the corpus, named with the
scheme it came from, because every one of them was a false positive during
development. A regex over eligibility prose is only as good as the sentences it
has been made to refuse, and these are the ones it got wrong.

The harm being guarded against is specific and one-directional: telling a family
living in a kutcha hut that they do not qualify for a housing scheme, because we
read "house" where the scheme wrote "pucca house".
"""

from __future__ import annotations

import pytest

from src.corpus.assets import extract


class TestWhatItReads:
    def test_the_commonest_rule_in_the_corpus(self):
        """A housing scheme excludes people who already have a house. Ten
        schemes say it about houses and seven about pucca houses."""
        rule = extract("1. The applicant should not have a pucca house.")
        assert rule.must_not_own == {"pucca_house"}
        assert not rule.must_own

    def test_pucca_is_not_widened_to_house(self):
        """The whole reason the two are separate facets. A family in a kutcha
        hut owns a house and does not own a pucca one; recording this as "owns
        no house" denies them every housing scheme they are entitled to."""
        rule = extract("The applicant should not own a pucca house.")
        assert "house" not in rule.must_not_own

    def test_a_requirement_to_own_is_read_as_one(self):
        """Direction is not implied by the asset. This is the aquarium subsidy,
        and reading it as an exclusion denies the grant to exactly the people
        who qualify."""
        rule = extract(
            "The applicant should possess a pucca house/commercial place "
            "to keep an aquarium.")
        assert rule.must_own == {"pucca_house"}
        assert not rule.must_not_own

    def test_the_family_scope_is_recorded(self):
        """"in his or any family member's name" is a materially wider bar, and
        somebody answering for themselves would answer the narrow question."""
        rule = extract(
            "The applicant or his/her family members must not own a pucca "
            "house in any part of the country.")
        assert rule.must_not_own == {"pucca_house"}
        assert rule.family_scope

    def test_vehicles(self):
        rule = extract(
            "1. The applicant should not possess any three/four-wheeler "
            "in his/her name.")
        assert rule.must_not_own == {"vehicle"}

    def test_boats(self):
        rule = extract("The applicant must own a mechanized fishing boat.")
        assert rule.must_own == {"boat"}

    def test_every_rule_carries_its_sentence(self):
        """So any single decision can be audited against the source by eye."""
        rule = extract("1. The beneficiary should not own any house or house site.")
        assert rule.evidence
        assert "should not own any house" in rule.evidence[0]


class TestWhatItRefuses:
    """Each of these produced a wrong rule at some point during development."""

    def test_a_prior_benefit_is_not_an_asset(self):
        """Subsidy to Purchase E-Bike for Journalists. "Should not have availed"
        is about a past transaction, not a present possession."""
        rule = extract(
            "The applicant should not have availed benefit to purchase an "
            "e-bike (two-wheeler) under any other Government scheme.")
        assert rule.empty

    def test_a_licence_is_not_a_vehicle(self):
        """Amma Two Wheeler Scheme, which exists to GIVE her the two-wheeler.
        Reading "possess a valid Two Wheeler / Learner License" as owning one
        inverts who the scheme is for."""
        rule = extract(
            "The applicant should know how to drive and possess a valid "
            "Two Wheeler / Learner License Registration (LLR) at the time "
            "of applying.")
        assert "vehicle" not in rule.must_own

    def test_a_pucca_cattle_shed_is_not_a_pucca_house(self):
        """Mukhyamantri Sudharit Kamdhenu Scheme. "Pucca" is an adjective, and
        this would have excluded a dairy farmer from every housing scheme."""
        rule = extract(
            "The applicant must possess a pucca cattle shed with cement "
            "flooring for housing the animals proposed to be reared.")
        assert "pucca_house" not in rule.must_own

    def test_a_residence_certificate_is_not_a_house(self):
        """The single biggest source of false positives. In this corpus
        "residence" almost always means domicile."""
        for text in (
            "The applicant must possess a 15 years residence certificate.",
            "The applicant, if applying as a Goan Scholar, must have 15 years "
            "of Residence in Goa.",
            "The applicant must have a valid Aadhaar-linked bank account, "
            "residence proof, income certificate and community certificate.",
        ):
            assert extract(text).empty, text

    def test_owning_land_to_build_a_house_on_is_a_land_rule(self):
        """Ved-Vyas Housing Construction Scheme. Recording it here would invent
        a housing condition out of a land one and exclude the landless family
        the scheme was written for."""
        rule = extract("1. The applicant must own land for house construction.")
        assert "house" not in rule.must_own

    def test_intending_to_buy_is_not_owning(self):
        """A cooperative loan for buying a boat. The whole point is that they
        do not own one yet."""
        rule = extract(
            "The beneficiary should have the intention to use the loan "
            "specifically for purchasing a fishing boat (Catamaran).")
        assert "boat" not in rule.must_own

    def test_experience_in_a_boat_is_not_a_boat(self):
        rule = extract(
            "In the case of male applicants, they should possess sea fishing "
            "experience in any mechanized boat for a minimum period of 5 years.")
        assert "boat" not in rule.must_own

    def test_have_before_a_participle_is_an_auxiliary(self):
        """Good Samaritan Scheme. "Should have saved the life of a victim of a
        fatal accident involving a motor vehicle" owns no vehicle."""
        rule = extract(
            "The applicant should have saved the life of a victim of a fatal "
            "accident involving a motor vehicle by administering immediate "
            "assistance.")
        assert "vehicle" not in rule.must_own

    def test_in_house_expertise_is_not_a_house(self):
        """AICTE Grant for Organizing Conference."""
        rule = extract(
            "1. The applicant institution should possess in-house expertise "
            "in the subject.")
        assert "house" not in rule.must_own

    def test_the_asset_must_be_the_object_of_the_verb(self):
        """Saksham Yuva Scheme. "The house of the applicant has a functional
        toilet" owns a toilet, and reads identically to a regex that will take
        a verb from either side of the noun."""
        rule = extract("1. That the house of the applicant has a functional toilet.")
        assert "house" not in rule.must_own

    def test_a_verb_is_not_taken_from_the_previous_sentence(self):
        """Yashwantrao Chavan Mukta Vasahat Yojana. With a fixed-width window
        the verb came from line one and the noun from line two, and a family
        living in a tent was recorded as owning a house."""
        rule = extract(
            "1. The family of the applicant should not be having their own house.\n"
            "1. The family of the applicant should be residing in a tent house or hut.")
        assert rule.must_not_own == {"house"}
        assert not rule.must_own


class TestWhatItFlagsRatherThanGuesses:
    def test_a_permitted_count_is_not_a_ban(self):
        """Dalit Bandhu permits one house. Flattening "not more than one" to
        "must own none" excludes a family the scheme was written to include."""
        rule = extract(
            "The family should not own more than 3 acres of agricultural land "
            "or more than one residential house.")
        assert rule.unquantified
        assert "house" not in rule.must_not_own

    def test_a_condition_on_the_house_is_not_a_condition_to_have_one(self):
        """Shubhshakti Yojana."""
        rule = extract(
            "1. If the beneficiary has his own house, there should be a "
            "toilet in the house.")
        assert rule.unquantified
        assert not rule.must_own

    def test_own_or_rented_is_neither(self):
        """Mukhya Mantri Shahri Ajeevika Guarantee Yojna."""
        rule = extract(
            "Meaning thereby they should be residing within the jurisdiction "
            "of the Urban Local Body either in their own house or on rent.")
        assert not rule.must_own

    def test_a_disqualification_written_backwards_is_flagged(self):
        """Ambedkar DBT Voucher Scheme states its rule as "the student whose
        parent owns a house ... is not eligible". The negation attaches to the
        eligibility, not to the verb, and inverting it automatically would be
        guessing."""
        rule = extract(
            "1. The student whose parent/guardian owns a house in the city or "
            "town where they are studying is not eligible for benefits under "
            "this scheme.")
        assert rule.unquantified
        assert not rule.must_own

    def test_a_scheme_that_both_requires_and_forbids_is_flagged(self):
        """Either we misread it or the prose is genuinely conditional. Both
        answers are a person, not a verdict."""
        rule = extract(
            "The applicant should not possess a house.\n"
            "The applicant should have a house site of an area of 450 sq.ft "
            "to build the house.")
        assert rule.unquantified

    def test_a_definition_is_not_this_scheme_s_rule(self):
        rule = extract(
            "Note: a homeless person is one who does not own a house.")
        assert not rule.must_not_own


class TestNothingIn:
    @pytest.mark.parametrize("text", [None, "", "   ",
                                      "The applicant must be 18 years old."])
    def test_nothing_out(self, text):
        assert extract(text).empty
