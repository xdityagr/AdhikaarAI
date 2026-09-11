"""
Choosing the next question — eight instead of eighty.

The corpus holds 4,736 schemes and fifteen dimensions that can restrict one. Ask
about all fifteen and nobody finishes; ask a fixed few and most of the corpus
never gets a chance to match. What the old wizard did was the second thing: the
welfare track asked three questions — what do you need, your community, your
state — and so three of fifteen dimensions were ever filled in. Occupation is the
single most restrictive facet in the corpus, named by 1,225 schemes, and it was
never asked. A weaver looking for a weaver's scheme was indistinguishable from
anyone else in Bihar.

THE SELECTION RULE

After every answer, look at the schemes still in play and ask the question the
most of them actually care about:

    score(facet) = |{candidate schemes that NAME that facet}|

Nothing more clever. A facet no candidate restricts on teaches us nothing, and a
facet half of them name splits the field. Targeting facets — caste, occupation,
disability, BPL — are weighted up, because `discovery.score()` already treats a
scheme that names a group you belong to as three times more interesting than one
that merely fails to exclude you, and the count that means something to a person
reading the result is `total_targeted`, not `total_matched`.

Measured on the real corpus, this produces genuinely different interviews:

    farming in Bihar      -> occupation, then employment status
    a pension in Kerala   -> occupation, then gender, then disability
    schooling in Tamil Nadu -> student status, then caste

Three people, three interviews, from counting alone.

NO MODEL DECIDES ANYTHING HERE. Which question comes next is a sort over integer
counts. The model's job is language — reading a typed answer that isn't one of
the chips — and it is not on this path at all.

SKIPPING IS FREE, AND THAT IS LOAD-BEARING

`discovery` is built on "absence is not negation": a scheme that names no caste
restricts nobody, so an unanswered question can never exclude a scheme. This
module must not quietly undo that. A skipped question is recorded as asked and
left unanswered — it stops being offered, and it takes nothing away. The test for
this is that skipping every question returns the same match count as answering
nothing at all.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.discovery import (
    _TARGETING,
    Facets,
    open_corpus,
)
from src.paths import CATALOGUE_DB

logger = logging.getLogger(__name__)

#: Stop here even if questions still score. Eight is the PS's own number and it
#: is about the person, not the corpus — there is always one more facet worth
#: asking, and the product that asks it loses the person who was going to answer.
MAX_QUESTIONS = 8

#: A question has to interest this share of the schemes still in play to be worth
#: a turn. Relative rather than a flat count, because a flat one silently ends the
#: interview as the field narrows: at 81 candidates a threshold of 12 stopped a
#: weaver after three questions while five useful facets still had something to
#: say. The floor stops us asking about a facet two schemes happen to mention.
MIN_SHARE = 0.04
MIN_INTERESTED = 3

#: Targeting facets decide `total_targeted`, which is the number that means
#: something to someone reading the result. Weighted to match `discovery.score`.
_TARGETING_WEIGHT = 3


@dataclass(frozen=True)
class Option:
    value: str
    label: str


@dataclass(frozen=True)
class Question:
    """One askable thing.

    `identifier` is the corpus's own facet name where there is one, because
    scoring counts schemes in `scheme_facets` and a name we invent matches
    nothing. `probe` names the alternative scorer for the two dimensions that
    live on columns rather than in the facet index.
    """
    id: str
    facet_field: str                  # the attribute on Facets this fills
    identifier: Optional[str] = None  # scheme_facets.identifier
    probe: Optional[str] = None       # "age" | "income" for column-backed ones
    options: tuple[Option, ...] = ()
    input: Optional[str] = None       # "amount" | "number" for typed answers
    targeting: bool = False
    #: English, and the last resort. Translations live in `src.i18n` under
    #: `ask_<id>`; this is what shows when one is missing, because an
    #: untranslated question should read as a question and not as a key.
    fallback_prompt: str = ""


# The corpus's exact strings. `occupation` is passed through unmapped by
# `discovery._label`, so these values must match myScheme's own vocabulary
# character for character or they filter to nothing. Ordered by how many schemes
# name them, so the common answers are the first ones a thumb reaches.
_OCCUPATIONS = (
    "Farmer", "Construction Worker", "Unorganized Worker", "Fishermen",
    "Artists", "Artisans, Spinners & Weavers", "Student", "Organized Worker",
    "Sportsperson", "Ex Servicemen", "Journalist", "Dairy Farmer",
    "Safai Karamchari", "Teacher / Faculty", "Street Vendor", "Coir Worker",
    "Health Worker", "Khadi Artisan", "Lawyer / Law Graduate / Advocate",
)

QUESTIONS: tuple[Question, ...] = (
    Question(
        id="occupation", facet_field="occupation", identifier="occupation",
        targeting=True,
        options=tuple(Option(o, o) for o in _OCCUPATIONS),
        fallback_prompt="What work do you do? It decides more schemes than anything else you can tell me.",
    ),
    Question(
        id="age", facet_field="age", probe="age", input="number",
        options=(Option("10", "Under 14"), Option("17", "14–17"),
                 Option("25", "18–30"), Option("40", "31–45"),
                 Option("52", "46–59"), Option("65", "60 or older")),
        fallback_prompt="How old are you?",
    ),
    Question(
        id="gender", facet_field="gender", identifier="gender",
        options=(Option("female", "Woman"), Option("male", "Man"),
                 Option("transgender", "Transgender")),
        fallback_prompt="Who is this for?",
    ),
    Question(
        id="caste", facet_field="caste", identifier="caste", targeting=True,
        options=(Option("sc", "SC"), Option("st", "ST"), Option("obc", "OBC"),
                 Option("pvtg", "PVTG"), Option("dnt", "DNT"),
                 Option("general", "General")),
        fallback_prompt="Which community do you belong to? Many schemes are reserved, and this is the only way to see them.",
    ),
    Question(
        id="employment", facet_field="employment_status",
        identifier="employmentStatus",
        options=(Option("employed", "Employed"),
                 Option("unemployed", "Unemployed"),
                 Option("self-employed", "Self-employed")),
        fallback_prompt="Are you working at the moment?",
    ),
    Question(
        id="student", facet_field="is_student", identifier="isStudent",
        targeting=True,
        options=(Option("yes", "Yes, studying"), Option("no", "No")),
        fallback_prompt="Are you studying right now?",
    ),
    Question(
        id="disability", facet_field="disability", identifier="disability",
        targeting=True,
        options=(Option("yes", "Yes"), Option("no", "No")),
        fallback_prompt="Do you have a disability certificate?",
    ),
    Question(
        id="marital", facet_field="marital_status", identifier="maritalStatus",
        options=(Option("never married", "Never married"),
                 Option("married", "Married"), Option("widowed", "Widowed"),
                 Option("divorced", "Divorced"),
                 Option("separated", "Separated")),
        fallback_prompt="Are you married?",
    ),
    Question(
        id="residence", facet_field="residence", identifier="residence",
        options=(Option("rural", "A village"), Option("urban", "A town or city")),
        fallback_prompt="Do you live in a village, or a town or city?",
    ),
    Question(
        id="bpl", facet_field="is_bpl", identifier="isBpl", targeting=True,
        options=(Option("yes", "Yes"), Option("no", "No")),
        fallback_prompt="Do you have a BPL ration card?",
    ),
    Question(
        id="minority", facet_field="minority", identifier="minority",
        targeting=True,
        options=(Option("yes", "Yes"), Option("no", "No")),
        fallback_prompt="Do you belong to a minority community?",
    ),
    Question(
        id="land", facet_field="land_acres", probe="land", input="number",
        targeting=True,
        options=(Option("0", "None — I don't own land"),
                 Option("0.5", "Under 1 acre"), Option("1.5", "1–2 acres"),
                 Option("3.5", "2–5 acres"), Option("8", "More than 5 acres")),
        fallback_prompt="How much farmland do you own? A rough figure is fine, and "
                        "owning none is an answer that opens schemes of its own.",
    ),
    Question(
        id="income", facet_field="family_income", probe="income", input="amount",
        options=(Option("60000", "Under ₹1 lakh"),
                 Option("150000", "₹1–2 lakh"),
                 Option("250000", "₹2–3 lakh"),
                 Option("400000", "₹3–5 lakh"),
                 Option("800000", "Above ₹5 lakh")),
        fallback_prompt="Roughly what does your whole household earn in a year? An estimate is fine.",
    ),
)

BY_ID = {q.id: q for q in QUESTIONS}


# ---------------------------------------------------------------------------
# The corpus side, loaded once
# ---------------------------------------------------------------------------
#
# `discover()` rebuilds the facet index on every call — a full scan of
# scheme_facets, ~9ms. That is nothing once, and it is not nothing when the
# interview asks it of every candidate facet on every turn. The corpus is a
# read-only build artefact pinned by tag, so caching it is safe in the strongest
# sense: the file cannot change under a running process without a redeploy.

_INDEX: Optional[dict[str, dict[str, set[str]]]] = None
_RESTRICTS: Optional[dict[str, set[str]]] = None


def _build(corpus_path: Path) -> None:
    """`{identifier: {slugs that restrict on it}}`, plus the age/income probes."""
    global _INDEX, _RESTRICTS
    conn = open_corpus(corpus_path)
    if conn is None:
        _INDEX, _RESTRICTS = {}, {}
        return
    try:
        index: dict[str, dict[str, set[str]]] = {}
        restricts: dict[str, set[str]] = {}
        for slug, identifier, value in conn.execute(
                "SELECT slug, identifier, value FROM scheme_facets"):
            index.setdefault(slug, {}).setdefault(identifier, set()).add(value)
            restricts.setdefault(identifier, set()).add(slug)

        # Age lives on columns, not in the facet index. `age_max = 100` is how
        # myScheme spells "no upper limit" — 1,970 schemes carry it — so treating
        # it as a real ceiling would make age look universally restrictive and
        # push it to the front of every interview.
        restricts["age"] = {
            row[0] for row in conn.execute(
                """SELECT slug FROM scheme_eligibility
                   WHERE (age_min IS NOT NULL AND age_min > 0)
                      OR (age_max IS NOT NULL AND age_max < 100)""")
        }
        # Income is thinner than intuition suggests: 544 schemes of 4,736 publish
        # any ceiling at all. It is worth asking, and it is not worth asking
        # first, and the score is what says so rather than a hand-written order.
        restricts["income"] = {
            row[0] for row in conn.execute(
                """SELECT slug FROM scheme_eligibility
                   WHERE family_income_max IS NOT NULL
                      OR individual_income_max IS NOT NULL
                      OR parent_income_max IS NOT NULL""")
        }
        # Land, extracted from prose by `src.corpus.land`. Guarded because a
        # corpus published before that pass has no such columns and asking would
        # raise on the first turn of every conversation.
        try:
            restricts["land"] = {
                row[0] for row in conn.execute(
                    """SELECT slug FROM scheme_eligibility
                       WHERE land_min_acres IS NOT NULL
                          OR land_max_acres IS NOT NULL
                          OR land_landless_required = 1
                          OR land_unquantified = 1""")
            }
        except sqlite3.OperationalError:
            restricts["land"] = set()
    finally:
        conn.close()
    _INDEX, _RESTRICTS = index, restricts


def _restricts(corpus_path: Path = CATALOGUE_DB) -> dict[str, set[str]]:
    if _RESTRICTS is None:
        _build(corpus_path)
    return _RESTRICTS or {}


def reset_cache() -> None:
    """Drop the cached index. For tests that swap the corpus underneath us."""
    global _INDEX, _RESTRICTS
    _INDEX = _RESTRICTS = None


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def lowered_words(text: str) -> set[str]:
    """Words of an answer, lowercased. Small enough to inline, named because
    `coerce` reads better when the intent is stated than when it is punctuation."""
    return set(re.findall(r"[a-z]+", text.lower()))


def _key(question: Question) -> str:
    return question.probe or question.identifier or question.id


def score_questions(
    candidate_slugs: set[str],
    asked: set[str],
    corpus_path: Path = CATALOGUE_DB,
) -> list[tuple[Question, int]]:
    """Every askable question with its weighted score, best first.

    The score is how many of the schemes still in play name that facet. It is a
    set intersection, so it costs nothing and can be shown to anyone who asks
    why a question was chosen.
    """
    restricts = _restricts(corpus_path)
    floor = max(MIN_INTERESTED, int(MIN_SHARE * len(candidate_slugs)))
    scored: list[tuple[Question, int]] = []
    for question in QUESTIONS:
        if question.id in asked:
            continue
        interested = restricts.get(_key(question), set()) & candidate_slugs
        if len(interested) < floor:
            continue
        weight = _TARGETING_WEIGHT if question.targeting else 1
        scored.append((question, len(interested) * weight))
    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    return scored


def next_question(
    candidate_slugs: set[str],
    asked: set[str],
    corpus_path: Path = CATALOGUE_DB,
) -> Optional[Question]:
    """The question worth asking now, or None when we should stop.

    Stops on two conditions: we have asked enough, or nothing left to ask clears
    the relevance floor in `score_questions`.
    """
    if len(asked) >= MAX_QUESTIONS:
        return None
    scored = score_questions(candidate_slugs, asked, corpus_path)
    return scored[0][0] if scored else None


def apply_answer(facets: Facets, question: Question, value: Any) -> Facets:
    """Set one answer on a Facets, leaving everything else alone.

    Returns the same object — Facets is a plain mutable dataclass and the caller
    owns it. A `None` value is a skip, and a skip writes nothing, which is what
    keeps an unanswered question from excluding anything.
    """
    if value is None:
        return facets
    setattr(facets, question.facet_field, value)
    return facets


def coerce(question: Question, raw: str) -> Optional[Any]:
    """Turn a chip value or a typed answer into what Facets wants.

    Returns None when it cannot be read, which the caller must treat as "ask
    again", never as "skip" — silently recording an unreadable answer as a skip
    is how someone ends up with results that do not reflect what they said.
    """
    text = (raw or "").strip()
    if not text:
        return None

    if question.probe == "land":
        # Zero is a real answer here and a meaningful one — landless households
        # are named by schemes of their own — so this cannot reuse the age
        # parser, which reads "0" as no answer and "0.5" as five.
        match = re.search(r"\d+(?:\.\d+)?", text)
        if match is None:
            if any(word in lowered_words(text)
                   for word in ("none", "no", "nil", "landless", "nothing")):
                return 0.0
            return None
        acres = float(match.group())
        return acres if 0 <= acres < 10_000 else None

    if question.probe == "age" or question.input == "number":
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return None
        age = int(digits)
        return age if 0 < age < 120 else None

    if question.probe == "income" or question.input == "amount":
        from src.chat import parse_amount        # local: chat imports us back
        return parse_amount(text)

    lowered = text.lower()
    # Yes/No flags become real booleans; everything else is a label the corpus
    # will recognise after discovery's own mapping.
    if {o.value for o in question.options} == {"yes", "no"}:
        if lowered in ("yes", "y", "haan", "हाँ", "true"):
            return True
        if lowered in ("no", "n", "nahi", "नहीं", "false"):
            return False
        return None

    for option in question.options:
        if lowered == option.value.lower() or lowered == option.label.lower():
            return option.value
    # Free text: accept a substring hit against the option labels, so "weaver"
    # finds "Artisans, Spinners & Weavers".
    for option in question.options:
        haystack = f"{option.value} {option.label}".lower()
        if any(word and word in haystack for word in lowered.split()):
            return option.value
    return None
