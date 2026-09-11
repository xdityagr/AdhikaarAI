"""
The household splits its facets the right way.

`web/lib/household.ts` decides which answers belong to the house and which to
the person, and that split is the whole design: get it wrong and either the
form asks four people for the same income, or a girl-child scholarship is
matched against her father's age.

The store itself is browser code with no test runner in front of it, so what is
checked here is the contract it shares with the engine — that every facet it
sends is one `Facets` actually accepts, and that none is silently dropped. A key
renamed on one side and not the other fails no build and simply stops matching.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.discovery import Facets

WEB = Path(__file__).resolve().parents[1] / "web" / "lib"
HOUSEHOLD = (WEB / "household.ts").read_text(encoding="utf-8")
FACETS_TS = (WEB / "facets.ts").read_text(encoding="utf-8")


def _keys(name: str) -> list[str]:
    """The string entries of an exported `const NAME = [...] as const`."""
    match = re.search(rf"export const {name} = \[(.*?)\] as const;",
                      HOUSEHOLD, re.S)
    assert match, f"{name} is not declared in household.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


SHARED = _keys("SHARED_KEYS")
MEMBER = _keys("MEMBER_KEYS")


class TestTheSplit:
    def test_the_house_owns_what_the_house_owns(self):
        """Income, state, residence and the ration card are the same number and
        the same card whoever is asking, and a scheme's income ceiling is
        written against the household anyway."""
        assert set(SHARED) == {
            "state", "residence", "caste", "family_income", "is_bpl"}

    def test_the_person_owns_what_varies(self):
        """These are exactly the facets that decide which member can claim
        what — a pension, a scholarship and a tool kit are told apart by age,
        gender and occupation, not by the household's income."""
        assert set(MEMBER) == {
            "age", "gender", "disability", "is_student", "occupation",
            "marital_status", "employment_status"}

    def test_nothing_is_in_both(self):
        """A facet on both sides would let a member silently override the
        household, or be overridden by it, depending on merge order."""
        assert not set(SHARED) & set(MEMBER)


class TestTheEngineAcceptsAllOfThem:
    @pytest.mark.parametrize("facet", SHARED + MEMBER)
    def test_facet_exists_on_the_matcher(self, facet):
        """Every key the household sends must be one `Facets` takes.

        This is the failure that shows up as "the household view stopped
        finding anything" with no error anywhere: a renamed facet is simply
        ignored by the request model and the match quietly widens.
        """
        assert facet in Facets.__dataclass_fields__, (
            f"household.ts sends '{facet}', which Facets does not accept"
        )

    def test_caste_is_shared_not_per_member(self):
        """A judgement call worth pinning down: it is what the certificate is
        issued against, and putting it per-member would double the questions
        for something that almost never varies within one house."""
        assert "caste" in SHARED and "caste" not in MEMBER


class TestItAgreesWithTheEligibilityForm:
    """The single-person check and the household must ask the same questions.

    They send to the same endpoint, and the household's "why did this person
    match?" link hands its answers straight to /check/results. A facet the
    wizard knows and the household does not is a scheme the household will
    never surface.
    """

    def test_every_household_facet_is_a_known_answer(self):
        answers = re.search(r"export interface Answers \{(.*?)\n\}",
                            FACETS_TS, re.S)
        assert answers
        known = set(re.findall(r"(\w+)\??:", answers.group(1)))
        for facet in SHARED + MEMBER:
            assert facet in known, (
                f"'{facet}' is not in Answers, so answersToPayload will drop it"
            )
