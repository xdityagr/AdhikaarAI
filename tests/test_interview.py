"""
Adaptive interview tests.

On a purpose-made corpus, never the real one — the ingest rewrites
`data/schemes.db`, and a test whose assertions depend on live crawl progress is a
flaky test.

Two properties matter more than any particular question order:

1. **Skipping is free.** `discovery` is built on "absence is not negation", and
   an interview that quietly narrowed the field when someone declined to answer
   would undo that without anyone noticing. Skipping every question must leave
   exactly the matches that answering nothing leaves.
2. **It ends.** Someone's attention is finite; the loop must terminate whether or
   not the corpus has run out of things to be curious about.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.corpus.myscheme import init_db
from src.discovery import CASTE_LABELS, Facets, discover
from src import interview
from src.interview import (
    MAX_QUESTIONS,
    apply_answer,
    coerce,
    next_question,
    score_questions,
)


# ---------------------------------------------------------------------------
# Fixture corpus
# ---------------------------------------------------------------------------

def _scheme(slug, name, *, state="All", categories=None, caste=None, gender=None,
            residence=None, occupation=None, employment=None, marital=None,
            flags=(), age_min=None, age_max=None, income_max=None):
    facets = []
    for identifier, values in (("caste", caste), ("gender", gender),
                               ("residence", residence), ("occupation", occupation),
                               ("employmentStatus", employment),
                               ("maritalStatus", marital)):
        for value in values or ():
            facets.append((slug, identifier, value))
    for identifier in flags:
        facets.append((slug, identifier, "Yes"))
    return {
        "scheme": {"slug": slug, "name": name, "level": "State", "state": state,
                   "categories": json.dumps(categories or []), "brief": "",
                   "eligibility_md": "prose"},
        "facets": facets,
        "eligibility": {"slug": slug, "age_min": age_min, "age_max": age_max,
                        "family_income_max": income_max},
    }


def _insert(conn, table, values: dict) -> None:
    cols = ", ".join(values)
    conn.execute(f"INSERT INTO {table} ({cols}) "
                 f"VALUES ({', '.join(f':{c}' for c in values)})", values)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    """Enough schemes that the relevance floor has something to bite on.

    Built with the ingest's own `init_db`, so a column renamed in the ingest
    breaks this test rather than breaking the interview silently in production.
    """
    path = tmp_path_factory.mktemp("interview-corpus") / "schemes.db"
    conn = sqlite3.connect(str(path))
    init_db(conn)

    rows = []
    # 30 occupation-restricted schemes — the facet that should dominate early.
    for i in range(30):
        rows.append(_scheme(f"weaver-{i}", f"Weaver Scheme {i}",
                            occupation=["Artisans, Spinners & Weavers"]))
    # 20 caste-restricted.
    for i in range(20):
        rows.append(_scheme(f"sc-{i}", f"SC Scheme {i}", caste=[CASTE_LABELS["sc"]]))
    # 12 gender-restricted.
    for i in range(12):
        rows.append(_scheme(f"women-{i}", f"Women Scheme {i}", gender=["Female"]))
    # 10 with a real age band.
    for i in range(10):
        rows.append(_scheme(f"elderly-{i}", f"Pension {i}", age_min=60, age_max=99))
    # 25 that restrict on nothing at all — they must never be excluded, and they
    # must never make a question look worth asking.
    for i in range(25):
        rows.append(_scheme(f"open-{i}", f"Open Scheme {i}"))

    for row in rows:
        _insert(conn, "schemes", row["scheme"])
        _insert(conn, "scheme_eligibility", row["eligibility"])
        for slug, identifier, value in row["facets"]:
            conn.execute("INSERT INTO scheme_facets (slug, identifier, value) "
                         "VALUES (?,?,?)", (slug, identifier, value))
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _fresh_cache():
    """The module caches the facet index; each test gets it rebuilt."""
    interview.reset_cache()
    yield
    interview.reset_cache()


def _all_slugs(corpus: Path) -> set[str]:
    conn = sqlite3.connect(str(corpus))
    slugs = {r[0] for r in conn.execute("SELECT slug FROM schemes")}
    conn.close()
    return slugs


# ---------------------------------------------------------------------------


class TestSelection:
    def test_it_asks_about_what_the_candidates_actually_restrict(self, corpus):
        """Occupation restricts 30 schemes here; nothing else comes close."""
        question = next_question(_all_slugs(corpus), asked=set(), corpus_path=corpus)
        assert question is not None
        assert question.id == "occupation"

    def test_a_facet_no_candidate_names_is_never_asked(self, corpus):
        """No fixture scheme requires BPL or minority status, so asking would
        spend a turn to learn nothing."""
        scored = score_questions(_all_slugs(corpus), asked=set(), corpus_path=corpus)
        offered = {q.id for q, _ in scored}
        assert "bpl" not in offered
        assert "minority" not in offered

    def test_asked_questions_are_not_asked_again(self, corpus):
        slugs = _all_slugs(corpus)
        first = next_question(slugs, asked=set(), corpus_path=corpus)
        second = next_question(slugs, asked={first.id}, corpus_path=corpus)
        assert second is not None
        assert second.id != first.id

    def test_two_different_people_get_different_questions(self, corpus):
        """The whole point. Restricted to the elderly-pension candidates, age is
        what matters; across the full corpus it is occupation."""
        everyone = next_question(_all_slugs(corpus), asked=set(), corpus_path=corpus)
        pensioners = {f"elderly-{i}" for i in range(10)} | {f"open-{i}" for i in range(25)}
        theirs = next_question(pensioners, asked=set(), corpus_path=corpus)
        assert everyone.id == "occupation"
        assert theirs.id == "age"

    def test_it_stops_after_max_questions(self, corpus):
        asked = {q.id for q in list(interview.QUESTIONS)[:MAX_QUESTIONS]}
        assert next_question(_all_slugs(corpus), asked=asked, corpus_path=corpus) is None

    def test_it_stops_when_nothing_is_left_to_ask(self, corpus):
        every_question = {q.id for q in interview.QUESTIONS}
        assert next_question(_all_slugs(corpus), asked=every_question,
                             corpus_path=corpus) is None

    def test_the_interview_always_terminates(self, corpus):
        """Loop it for real. Never answering is the worst case for termination,
        because the candidate set never shrinks."""
        asked, turns = set(), 0
        while (q := next_question(_all_slugs(corpus), asked, corpus_path=corpus)):
            asked.add(q.id)
            turns += 1
            assert turns <= MAX_QUESTIONS, "interview did not terminate"
        assert turns <= MAX_QUESTIONS


class TestSkippingIsFree:
    def test_skipping_every_question_hides_nothing(self, corpus):
        """The property that keeps absence-is-not-negation true end to end."""
        answered_nothing = discover(Facets(), limit=5000, corpus_path=corpus)

        facets, asked = Facets(), set()
        while (q := next_question(_all_slugs(corpus), asked, corpus_path=corpus)):
            asked.add(q.id)
            apply_answer(facets, q, None)          # a skip writes nothing

        after_skipping = discover(facets, limit=5000, corpus_path=corpus)
        assert after_skipping.total_matched == answered_nothing.total_matched

    def test_apply_answer_ignores_none(self, corpus):
        facets = Facets()
        apply_answer(facets, interview.BY_ID["caste"], None)
        assert facets.caste is None

    def test_an_unreadable_answer_is_not_silently_a_skip(self, corpus):
        """`coerce` returns None so the caller re-asks. Recording gibberish as a
        skip would give someone results that do not reflect what they said."""
        assert coerce(interview.BY_ID["caste"], "qwertyuiop") is None
        assert coerce(interview.BY_ID["age"], "no idea") is None


class TestCoercion:
    def test_chip_values_round_trip(self):
        assert coerce(interview.BY_ID["caste"], "sc") == "sc"
        assert coerce(interview.BY_ID["gender"], "female") == "female"

    def test_labels_are_accepted_too(self):
        assert coerce(interview.BY_ID["gender"], "Woman") == "female"

    def test_free_text_finds_the_occupation(self):
        """'weaver' has to reach 'Artisans, Spinners & Weavers' — the corpus's
        own string, which nobody would ever type."""
        assert coerce(interview.BY_ID["occupation"],
                      "weaver") == "Artisans, Spinners & Weavers"

    def test_yes_no_becomes_a_real_boolean(self):
        assert coerce(interview.BY_ID["disability"], "yes") is True
        assert coerce(interview.BY_ID["disability"], "no") is False

    def test_age_is_read_as_a_number_and_bounded(self):
        assert coerce(interview.BY_ID["age"], "65") == 65
        assert coerce(interview.BY_ID["age"], "I am 34 years old") == 34
        assert coerce(interview.BY_ID["age"], "900") is None

    def test_applying_an_answer_reaches_the_right_facet_field(self):
        facets = Facets()
        apply_answer(facets, interview.BY_ID["occupation"], "Farmer")
        apply_answer(facets, interview.BY_ID["age"], 45)
        assert facets.occupation == "Farmer"
        assert facets.age == 45
