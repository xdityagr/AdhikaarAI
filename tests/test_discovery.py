"""
Scheme discovery tests.

Built on a purpose-made fixture corpus, never the real one — the ingest rewrites
`data/schemes.db` and a test that depends on live crawl progress is a flaky test.

The rule under test throughout is **absence is not negation**. For a product that
exists because people never hear about schemes, wrongly hiding one is far worse
than showing one that turns out not to fit, so every unanswered question must
leave a scheme in the results.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.discovery import (
    CASTE_LABELS,
    Facets,
    MatchStrength,
    discover,
    discover_with_credit,
    open_corpus,
    score,
)
from src.corpus.myscheme import init_db
from src.schemes import UserProfile


# ---------------------------------------------------------------------------
# Fixture corpus
# ---------------------------------------------------------------------------

def _scheme(slug, name, *, level="State", state=None, categories=None, brief="",
            caste=None, gender=None, residence=None, occupation=None,
            flags=(), income_max=None, income_min=None,
            age_min=None, age_max=None):
    """One fixture scheme.

    Membership criteria go to `scheme_facets` and numeric bands to
    `scheme_eligibility`, exactly as the ingest splits them, so these tests
    exercise the same two-table read the product does.
    """
    facets = []
    for identifier, values in (("caste", caste), ("gender", gender),
                               ("residence", residence), ("occupation", occupation)):
        for value in values or ():
            facets.append((slug, identifier, value))
    for identifier in flags:
        facets.append((slug, identifier, "Yes"))

    return {
        "scheme": {
            "slug": slug, "name": name, "level": level, "state": state,
            "categories": json.dumps(categories or []), "brief": brief,
            "eligibility_md": "Eligibility prose for " + name,
        },
        "facets": facets,
        "eligibility": {
            "slug": slug,
            "family_income_min": income_min, "family_income_max": income_max,
            "age_min": age_min, "age_max": age_max,
        },
    }


def _insert(conn, table, values: dict) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join(f":{c}" for c in values)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    """A small corpus built with the ingest's OWN schema.

    Importing `init_db` rather than hand-writing CREATE TABLE means a column
    renamed in the ingest breaks this test instead of breaking discovery
    silently in production.
    """
    path = tmp_path_factory.mktemp("corpus") / "schemes.db"
    conn = sqlite3.connect(str(path))
    init_db(conn)
    rows = [
        # Open to everyone, nationwide: named in no facet at all, which is how
        # the real corpus represents "no restriction".
        _scheme("open-national", "Open National Scheme", level="Central", state="All"),
        # Targeted at SC — should outrank the generic one for an SC user.
        _scheme("sc-targeted", "SC Targeted Scheme", state="All",
                caste=[CASTE_LABELS["sc"]]),
        # Targeted at ST — must NOT reach an SC user.
        _scheme("st-only", "ST Only Scheme", state="All", caste=[CASTE_LABELS["st"]]),
        # State-specific.
        _scheme("up-only", "Uttar Pradesh Scheme", state="Uttar Pradesh"),
        _scheme("bihar-only", "Bihar Scheme", state="Bihar"),
        # Income ceiling.
        _scheme("low-income", "Low Income Scheme", state="All", income_max=100_000),
        # Age band.
        _scheme("elderly", "Old Age Pension", state="All", age_min=60, age_max=120),
        # Yes-only flag requirements.
        _scheme("bpl-only", "BPL Scheme", state="All", flags=["isBpl"]),
        _scheme("disability-only", "Disability Scheme", state="All",
                flags=["disability"]),
        # Occupation.
        _scheme("safai", "Safai Karamchari Scheme", state="All",
                occupation=["Safai Karamchari"]),
        # Women-only, to prove gender excludes in one direction only.
        _scheme("women-only", "Women Only Scheme", state="All", gender=["Female"]),
        # No structured eligibility at all — the mid-crawl case.
        _scheme("unknown-rules", "Scheme With No Structured Rules", state="All"),
    ]
    for row in rows:
        _insert(conn, "schemes", row["scheme"])
        conn.executemany(
            "INSERT INTO scheme_facets (slug, identifier, value) VALUES (?,?,?)",
            row["facets"])
        if row["scheme"]["slug"] != "unknown-rules":
            # Left out on purpose: mid-crawl, most schemes have no row yet, and
            # the LEFT JOIN must still return them.
            _insert(conn, "scheme_eligibility", row["eligibility"])
    conn.commit()
    conn.close()
    return path


def names(result) -> set[str]:
    return {m.slug for m in result.matches}


# ---------------------------------------------------------------------------
# Absence is not negation — the load-bearing rule
# ---------------------------------------------------------------------------

class TestAbsenceIsNotNegation:
    def test_empty_profile_excludes_nothing(self, corpus):
        """Someone who has answered nothing must still see everything."""
        result = discover(Facets(), limit=100, corpus_path=corpus)
        assert len(result.matches) == result.total_considered

    def test_unanswered_facet_does_not_exclude(self, corpus):
        """The scheme restricts by caste; the user hasn't said. Keep it, flag it."""
        result = discover(Facets(state="All"), limit=100, corpus_path=corpus)
        assert "sc-targeted" in names(result)
        match = next(m for m in result.matches if m.slug == "sc-targeted")
        assert "caste" in match.unknown
        assert match.strength is MatchStrength.CHECK

    def test_scheme_with_no_structured_rules_still_matches(self, corpus):
        """Mid-crawl, most schemes have no eligibility row yet. They must survive."""
        result = discover(Facets(caste="sc", family_income=50_000), limit=100,
                          corpus_path=corpus)
        assert "unknown-rules" in names(result)

    def test_null_flag_is_not_a_requirement(self, corpus):
        """is_bpl NULL means the scheme is silent — not that BPL is required."""
        result = discover(Facets(is_bpl=False), limit=100, corpus_path=corpus)
        assert "open-national" in names(result)


# ---------------------------------------------------------------------------
# Definite mismatches — these SHOULD exclude
# ---------------------------------------------------------------------------

class TestDefiniteMismatch:
    def test_wrong_caste_is_excluded_with_a_reason(self, corpus):
        result = discover(Facets(caste="sc"), limit=100, corpus_path=corpus)
        assert "st-only" not in names(result)
        rejected = next(m for m in result.not_matched if m.slug == "st-only")
        assert "caste" in rejected.unmet

    def test_other_states_are_excluded(self, corpus):
        result = discover(Facets(state="Uttar Pradesh"), limit=100, corpus_path=corpus)
        assert "up-only" in names(result)
        assert "bihar-only" not in names(result)

    def test_central_schemes_reach_every_state(self, corpus):
        """The 'All' trap: filtering by state must not hide national schemes."""
        result = discover(Facets(state="Uttar Pradesh"), limit=100, corpus_path=corpus)
        assert "open-national" in names(result)

    def test_income_over_the_ceiling_is_excluded(self, corpus):
        result = discover(Facets(family_income=150_000), limit=100, corpus_path=corpus)
        assert "low-income" not in names(result)

    def test_income_exactly_at_the_ceiling_qualifies(self, corpus):
        """≤ not < — the same boundary rule the NSFDC engine uses."""
        result = discover(Facets(family_income=100_000), limit=100, corpus_path=corpus)
        assert "low-income" in names(result)

    def test_age_outside_the_band_is_excluded(self, corpus):
        assert "elderly" not in names(discover(Facets(age=30), limit=100, corpus_path=corpus))
        assert "elderly" in names(discover(Facets(age=65), limit=100, corpus_path=corpus))

    def test_flag_requirement_excludes_when_user_says_no(self, corpus):
        result = discover(Facets(is_bpl=False), limit=100, corpus_path=corpus)
        assert "bpl-only" not in names(result)

    def test_flag_requirement_matches_when_user_says_yes(self, corpus):
        result = discover(Facets(is_bpl=True), limit=100, corpus_path=corpus)
        assert "bpl-only" in names(result)

    def test_occupation_targeting(self, corpus):
        """Safai Karamchari is a real myScheme occupation and a core MoSJE group."""
        assert "safai" in names(discover(Facets(occupation="Safai Karamchari"),
                                         limit=100, corpus_path=corpus))
        assert "safai" not in names(discover(Facets(occupation="Farmer"),
                                             limit=100, corpus_path=corpus))


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

class TestRelevance:
    def test_targeted_scheme_outranks_generic_one(self, corpus):
        """An SC applicant should see the SC scheme above the open one."""
        result = discover(Facets(caste="sc", state="All"), limit=100, corpus_path=corpus)
        order = [m.slug for m in result.matches]
        assert order.index("sc-targeted") < order.index("open-national")

    def test_unanswered_questions_cost_relevance(self, corpus):
        from src.discovery import DiscoveryMatch
        known = DiscoveryMatch("x", "x", "X", MatchStrength.LIKELY, matched_on=["caste"])
        unknown = DiscoveryMatch("y", "y", "Y", MatchStrength.LIKELY, unknown=["caste"])
        assert score(known, Facets()) > score(unknown, Facets())


# ---------------------------------------------------------------------------
# Honesty of the verdict
# ---------------------------------------------------------------------------

class TestVerdictHonesty:
    def test_myscheme_results_are_never_better_than_likely(self, corpus):
        """We have not read 4,772 prose rules. Never claim ELIGIBLE for them."""
        result = discover(Facets(caste="sc", family_income=50_000, age=30,
                                 gender="female", is_bpl=True, state="All"),
                          limit=100, corpus_path=corpus)
        assert result.matches
        assert all(m.strength is not MatchStrength.ELIGIBLE for m in result.matches)

    def test_nsfdc_schemes_do_carry_a_real_verdict(self, corpus):
        """For the five we model completely, ELIGIBLE is honest."""
        profile = UserProfile(project_type="business", project_cost=120_000,
                              annual_income=280_000, gender="female")
        result = discover_with_credit(Facets(caste="sc"), profile=profile,
                                      limit=100, corpus_path=corpus)
        deep = [m for m in result.matches if m.depth == "DEEP"]
        assert deep, "NSFDC schemes should be included"
        assert all(m.strength is MatchStrength.ELIGIBLE for m in deep)
        assert result.matches[0].depth == "DEEP", "verified schemes lead"

    def test_every_scheme_links_back_to_its_source(self, corpus):
        result = discover(Facets(), limit=100, corpus_path=corpus)
        assert all(m.source_url.startswith("https://") for m in result.matches)


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------

class TestMissingCorpus:
    def test_absent_corpus_degrades_instead_of_raising(self, tmp_path):
        """No corpus means NSFDC-only, not a stack trace in front of a user."""
        result = discover(Facets(), corpus_path=tmp_path / "nope.db")
        assert result.corpus_available is False
        assert result.matches == []

    def test_open_corpus_returns_none_when_missing(self, tmp_path):
        assert open_corpus(tmp_path / "nope.db") is None


# ---------------------------------------------------------------------------
# The facet index
# ---------------------------------------------------------------------------

class TestFacetIndex:
    def test_machine_values_map_to_exact_myscheme_labels(self, corpus):
        """The trap: the corpus stores 'Scheduled Caste (SC)', never 'SC'.

        Querying the abbreviation returns zero results with no error, so a user
        typing 'sc' must be translated before matching, not after.
        """
        assert "sc-targeted" in names(discover(Facets(caste="sc"), limit=100,
                                               corpus_path=corpus))
        assert "sc-targeted" in names(discover(Facets(caste=CASTE_LABELS["sc"]),
                                               limit=100, corpus_path=corpus))

    def test_unmapped_caste_does_not_silently_match_everything(self, corpus):
        """A value we cannot map is passed through and simply fails to match —
        it must never be dropped, which would make the filter disappear."""
        result = discover(Facets(caste="nonsense"), limit=100, corpus_path=corpus)
        assert "sc-targeted" not in names(result)
        assert "open-national" in names(result)   # unrestricted scheme still shows

    def test_scheme_in_no_facet_is_never_flagged_unknown(self, corpus):
        """An unrestricted scheme has nothing to ask about, so asking would be
        noise — 'we need to check your caste' on a scheme open to all castes."""
        result = discover(Facets(), limit=100, corpus_path=corpus)
        match = next(m for m in result.matches if m.slug == "open-national")
        assert match.unknown == []
        assert match.strength is MatchStrength.LIKELY

    def test_gender_excludes_in_one_direction_only(self, corpus):
        result_male = discover(Facets(gender="male"), limit=100, corpus_path=corpus)
        result_female = discover(Facets(gender="female"), limit=100, corpus_path=corpus)
        assert "women-only" not in names(result_male)
        assert "women-only" in names(result_female)

    def test_transgender_maps_to_the_corpus_value(self, corpus):
        from src.discovery import GENDER_LABELS
        assert GENDER_LABELS["transgender"] == "Transgender"

    def test_flag_facets_cover_every_yes_only_identifier(self):
        """If the ingest starts indexing a new Yes/No facet, matching must know
        about it — an unhandled identifier would silently stop filtering."""
        from src.discovery import _FACET_LABELS, _FLAG_FACETS
        from src.corpus.myscheme import MATCHING_FACETS
        handled = set(_FLAG_FACETS) | set(_FACET_LABELS)
        # 'age' and income come from the eligibility bands, not the facet index.
        unhandled = set(MATCHING_FACETS) - handled
        assert not unhandled, f"facet(s) crawled but never matched on: {unhandled}"


# ---------------------------------------------------------------------------
# The words people actually use
# ---------------------------------------------------------------------------

class TestVocabulary:
    """A word we fail to map is not a harmless miss.

    It passes through unchanged, matches no facet value, and silently hides
    every scheme reserved for that community — while still returning hundreds of
    generic results, so nothing looks wrong. This came from watching a language
    model return "Dalit" where the corpus says "Scheduled Caste (SC)".
    """

    def test_dalit_and_sc_are_the_same_search(self, corpus):
        from src.discovery import CASTE_LABELS
        assert CASTE_LABELS["dalit"] == CASTE_LABELS["sc"]
        plain = discover(Facets(caste="sc"), limit=100, corpus_path=corpus)
        spoken = discover(Facets(caste="Dalit"), limit=100, corpus_path=corpus)
        assert names(plain) == names(spoken)

    def test_lookup_is_case_insensitive(self, corpus):
        for word in ("SC", "sc", "Scheduled Caste", "scheduled caste (SC)"):
            result = discover(Facets(caste=word), limit=100, corpus_path=corpus)
            assert "sc-targeted" in names(result), word
            assert "st-only" not in names(result), word

    def test_adivasi_reaches_scheduled_tribe_schemes(self, corpus):
        result = discover(Facets(caste="adivasi"), limit=100, corpus_path=corpus)
        assert "st-only" in names(result)
        assert "sc-targeted" not in names(result)

    def test_spoken_gender_and_residence_words_map(self, corpus):
        assert "women-only" in names(
            discover(Facets(gender="woman"), limit=100, corpus_path=corpus))
        assert "women-only" not in names(
            discover(Facets(gender="man"), limit=100, corpus_path=corpus))
        from src.discovery import RESIDENCE_LABELS
        assert RESIDENCE_LABELS["village"] == RESIDENCE_LABELS["rural"]
        assert RESIDENCE_LABELS["city"] == RESIDENCE_LABELS["urban"]

    def test_every_synonym_points_at_a_real_corpus_value(self):
        """A synonym mapping to a string the corpus does not use is worse than
        no synonym: it looks handled and returns nothing."""
        from src.discovery import CASTE_LABELS, GENDER_LABELS, RESIDENCE_LABELS
        real_caste = {
            "Scheduled Caste (SC)", "Scheduled Tribe (ST)",
            "Other Backward Class (OBC)", "General",
            "Particularly Vulnerable Tribal Group (PVTG)",
            "De-Notified, Nomadic, and Semi-Nomadic (DNT) communities",
        }
        assert set(CASTE_LABELS.values()) <= real_caste
        assert set(GENDER_LABELS.values()) <= {"Female", "Male", "Transgender"}
        assert set(RESIDENCE_LABELS.values()) <= {"Rural", "Urban"}
