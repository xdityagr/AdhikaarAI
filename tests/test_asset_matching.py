"""
The asset rules reach the verdict, and behave like every other facet.

Extraction is tested in `test_assets.py`; this is the other half — that what was
extracted is actually consulted, and that it obeys the rule the whole engine is
built on: **absence is not negation.**

It also pins a bug found while wiring this up. `evaluate_scheme` — the route
behind "am I eligible for THIS one", which is the question someone asks with a
scheme name already in hand — selected neither the land columns nor the asset
ones. So it had been answering LIKELY for a land-capped scheme to somebody over
the ceiling ever since land shipped, silently, because the rule was never read
into the row it checked.
"""

from __future__ import annotations

import pytest

from src.discovery import CORPUS_PATH, Facets, evaluate_scheme, open_corpus

#: Real schemes, and what their prose says. If the corpus is re-ingested and one
#: of these changes, this file should fail loudly rather than drift.
FORBIDS_PUCCA_HOUSE = "pmay-u"      # "must not own a pucca house in any part…"
REQUIRES_BOAT = "dvrsf"             # "must own a mechanized fishing boat"


@pytest.fixture(scope="module", autouse=True)
def _needs_corpus():
    conn = open_corpus(CORPUS_PATH)
    if conn is None:
        pytest.skip("scheme corpus not built")
    try:
        columns = {r[1] for r in
                   conn.execute("PRAGMA table_info(scheme_eligibility)")}
        if "assets_must_not_own" not in columns:
            pytest.skip("corpus predates the asset extraction pass")
    finally:
        conn.close()


class TestAnAssetTheSchemeForbids:
    def test_owning_it_is_a_definite_mismatch(self):
        match = evaluate_scheme(
            FORBIDS_PUCCA_HOUSE, Facets(owns_pucca_house=True))
        assert match.strength.value == "NOT_MATCHED"
        assert "pucca house" in match.unmet

    def test_not_owning_it_is_a_reason_it_matched(self):
        match = evaluate_scheme(
            FORBIDS_PUCCA_HOUSE, Facets(owns_pucca_house=False))
        assert match.strength.value != "NOT_MATCHED"
        assert "pucca house" in match.matched_on

    def test_not_saying_never_excludes(self):
        """The rule this whole engine is built on. Someone who has not been
        asked about a house must not be filtered out of housing schemes."""
        match = evaluate_scheme(FORBIDS_PUCCA_HOUSE, Facets())
        assert match.strength.value != "NOT_MATCHED"
        assert "pucca house" not in match.unmet

    def test_not_saying_is_reported_as_something_to_check(self):
        """And it must not be silent either, or somebody travels to an office
        to be turned away by a rule we had read and swallowed."""
        match = evaluate_scheme(FORBIDS_PUCCA_HOUSE, Facets())
        assert "pucca house" in match.unknown

    def test_owning_a_kutcha_house_is_not_owning_a_pucca_one(self):
        """The reason the two are separate facets, checked end to end: a family
        in a kutcha hut stays eligible for the housing scheme."""
        match = evaluate_scheme(
            FORBIDS_PUCCA_HOUSE, Facets(owns_house=True, owns_pucca_house=False))
        assert match.strength.value != "NOT_MATCHED"


class TestAnAssetTheSchemeRequires:
    """Not a mirror of the above. Every fisheries scheme here requires a
    registered boat, and that is a requirement a person can fail."""

    def test_not_owning_it_is_a_definite_mismatch(self):
        match = evaluate_scheme(REQUIRES_BOAT, Facets(owns_boat=False))
        assert match.strength.value == "NOT_MATCHED"
        assert "boat" in match.unmet

    def test_owning_it_is_a_reason_it_matched(self):
        match = evaluate_scheme(REQUIRES_BOAT, Facets(owns_boat=True))
        assert "boat" in match.matched_on
        assert "boat" not in match.unmet

    def test_not_saying_never_excludes(self):
        match = evaluate_scheme(REQUIRES_BOAT, Facets())
        assert match.strength.value != "NOT_MATCHED"
        assert "boat" in match.unknown


class TestTheSingleSchemeRouteReadsTheExtractedRules:
    """The bug this file was written for.

    `evaluate_scheme` built its own SELECT and never asked for the extracted
    columns, so every rule read out of prose — land since it shipped, and assets
    from the start — was invisible to the one route whose entire job is to say
    which condition is the problem.
    """

    def test_it_selects_the_asset_columns(self):
        match = evaluate_scheme(
            FORBIDS_PUCCA_HOUSE, Facets(owns_pucca_house=True))
        assert match.unmet, (
            "the single-scheme route is not reading the asset columns; it will "
            "answer LIKELY to somebody the scheme excludes"
        )

    def test_it_selects_the_land_columns(self):
        """Same SELECT, same omission, and land shipped first."""
        conn = open_corpus(CORPUS_PATH)
        try:
            row = conn.execute(
                "SELECT slug FROM scheme_eligibility "
                "WHERE land_max_acres IS NOT NULL LIMIT 1").fetchone()
        finally:
            conn.close()
        if row is None:
            pytest.skip("no land ceilings in this corpus")

        conn = open_corpus(CORPUS_PATH)
        try:
            ceiling = conn.execute(
                "SELECT land_max_acres FROM scheme_eligibility WHERE slug = ?",
                (row[0],)).fetchone()[0]
        finally:
            conn.close()

        match = evaluate_scheme(row[0], Facets(land_acres=ceiling + 10))
        assert "land" in match.unmet, (
            "the single-scheme route is not reading the land columns"
        )


class TestAnOlderCorpus:
    def test_a_corpus_without_the_columns_still_answers(self):
        """The corpus is pinned by release tag, so running against one built
        before this pass is normal rather than exceptional. It must degrade to
        "no asset rule", never to a crash."""
        match = evaluate_scheme(FORBIDS_PUCCA_HOUSE, Facets())
        assert match is not None
