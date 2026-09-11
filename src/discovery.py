"""
Scheme discovery — matching a person against the national corpus.

Two families of scheme, one engine:

- **NSFDC credit (DEEP)** — five schemes we model completely. Every published rule
  is evaluated, so the verdict can honestly be ELIGIBLE. Handled by the existing
  `src/schemes.py`, which this module wraps rather than replaces.
- **myScheme (DISCOVERY)** — ~4,736 welfare schemes. We hold who each one targets
  and its published income and age bands, but its prose adds conditions we have
  not read. The verdict is therefore never better than LIKELY.

Membership matching reads `scheme_facets`, the index the ingest builds by asking
the API one filtered query per facet value. It is used rather than the per-scheme
eligibility blob for two reasons: it covers the entire corpus rather than only the
schemes the slower detail crawl has reached, and its per-value counts are checked
against the API's own aggregations, so we can prove it is complete.

THE RULE THAT MATTERS MOST: **absence is not negation.**

A scheme missing from an identifier sits in that identifier's "All" bucket — it
restricts nobody. A scheme absent from `isBpl` does not require a BPL card; it is
silent, and silence is not "No". No published income ceiling is not a ceiling of
zero.

So a facet excludes ONLY when the scheme specifically names values and the user is
not among them. Filtering is inclusive by default, deliberately: for a product
whose whole reason to exist is "she never heard of it", wrongly hiding a scheme is
far worse than showing one that turns out not to fit. A scheme that fails a check
is demoted into a "not a match, and why" list — never silently dropped.

Nothing here calls a model. Matching is set membership and numeric comparison over
the structured corpus; the prose is shown verbatim as evidence and never decides.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.schemes import UserProfile, evaluate_eligibility

logger = logging.getLogger(__name__)

from src.paths import CATALOGUE_DB as CORPUS_PATH

MYSCHEME_URL = "https://www.myscheme.gov.in/schemes/{slug}"


class MatchStrength(str, Enum):
    """How confident we are, and we are never more confident than we should be."""
    ELIGIBLE = "ELIGIBLE"        # DEEP only: every published rule evaluated
    LIKELY = "LIKELY"            # structured criteria pass; prose may add more
    CHECK = "CHECK"              # passes, but names criteria the user hasn't given
    NOT_MATCHED = "NOT_MATCHED"


@dataclass
class Facets:
    """What we know about the person. Every field optional — an unanswered
    question must never exclude a scheme."""
    caste: Optional[str] = None            # sc | st | obc | pvtg | dnt | general
    gender: Optional[str] = None           # female | male | transgender
    age: Optional[int] = None
    state: Optional[str] = None
    residence: Optional[str] = None        # Rural | Urban
    family_income: Optional[float] = None
    is_bpl: Optional[bool] = None
    disability: Optional[bool] = None
    minority: Optional[bool] = None
    is_student: Optional[bool] = None
    occupation: Optional[str] = None
    employment_status: Optional[str] = None
    marital_status: Optional[str] = None
    is_gov_employee: Optional[bool] = None
    is_economic_distress: Optional[bool] = None
    categories: list[str] = field(default_factory=list)


@dataclass
class DiscoveryMatch:
    scheme_uid: str
    slug: str
    name: str
    strength: MatchStrength
    level: Optional[str] = None
    state: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    brief: Optional[str] = None
    eligibility_md: Optional[str] = None
    source_url: str = ""
    depth: str = "DISCOVERY"
    matched_on: list[str] = field(default_factory=list)   # facets the scheme names and the user meets
    unknown: list[str] = field(default_factory=list)      # scheme names it, user hasn't said
    unmet: list[str] = field(default_factory=list)        # why it did not match
    relevance: float = 0.0


@dataclass
class DiscoveryResult:
    matches: list[DiscoveryMatch] = field(default_factory=list)
    not_matched: list[DiscoveryMatch] = field(default_factory=list)
    total_considered: int = 0
    corpus_available: bool = True
    # Counted before the list is trimmed for display. The headline "you match
    # 1,204 schemes" has to be the real figure, not the size of the first page.
    total_matched: int = 0
    total_not_matched: int = 0
    strength_counts: dict = field(default_factory=dict)
    # Matches that name a group this person belongs to — their caste, their
    # occupation, their BPL card. With few answers almost everything "matches",
    # because a scheme that restricts nothing excludes nobody; this is the count
    # that actually means something to the person reading it.
    total_targeted: int = 0


# ---------------------------------------------------------------------------
# Corpus access
# ---------------------------------------------------------------------------

def open_corpus(path: Path = CORPUS_PATH) -> Optional[sqlite3.Connection]:
    """Read-only handle on the scheme corpus.

    Read-only because the corpus is a build artifact that an ingest may be
    rewriting. Returns None rather than raising when it hasn't been built — a
    missing corpus degrades the product to NSFDC-only, it does not break it.
    """
    if not path.exists():
        logger.warning("Scheme corpus not found at %s — discovery limited to NSFDC", path)
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_facet_index(conn: sqlite3.Connection) -> dict[str, dict[str, set[str]]]:
    """`{slug: {identifier: {values}}}` for the whole corpus.

    Loaded in one query and held in memory — it is a few thousand short strings,
    and doing it per-scheme would turn one query into thousands.
    """
    index: dict[str, dict[str, set[str]]] = {}
    for slug, identifier, value in conn.execute(
            "SELECT slug, identifier, value FROM scheme_facets"):
        index.setdefault(slug, {}).setdefault(identifier, set()).add(value)
    return index


def _json_list(raw: Any) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Facet labels
#
# myScheme's facet values are exact strings and nothing else works: querying
# "SC" instead of "Scheduled Caste (SC)" returns HTTP 200 with zero results and
# no error. These are copied verbatim from the ingested corpus, never typed from
# memory, and `scripts/check_facet_labels.py` fails the build if one drifts.
# ---------------------------------------------------------------------------

# Keys are lowercased on lookup, and the synonyms matter more than they look.
# People say "Dalit", not "Scheduled Caste (SC)", and so does a language model
# repeating what they said. An unmapped word passes through unchanged, fails to
# match the facet, and silently hides every scheme reserved for that community —
# the exact failure this product exists to prevent.
CASTE_LABELS = {
    "sc": "Scheduled Caste (SC)",
    "dalit": "Scheduled Caste (SC)",
    "scheduled caste": "Scheduled Caste (SC)",
    "scheduled caste (sc)": "Scheduled Caste (SC)",
    "dalit (scheduled caste)": "Scheduled Caste (SC)",
    "harijan": "Scheduled Caste (SC)",

    "st": "Scheduled Tribe (ST)",
    "adivasi": "Scheduled Tribe (ST)",
    "tribal": "Scheduled Tribe (ST)",
    "scheduled tribe": "Scheduled Tribe (ST)",
    "scheduled tribe (st)": "Scheduled Tribe (ST)",

    "obc": "Other Backward Class (OBC)",
    "other backward class": "Other Backward Class (OBC)",
    "other backward classes": "Other Backward Class (OBC)",
    "backward class": "Other Backward Class (OBC)",
    "bc": "Other Backward Class (OBC)",

    "general": "General",
    "gen": "General",
    "unreserved": "General",

    "pvtg": "Particularly Vulnerable Tribal Group (PVTG)",
    "particularly vulnerable tribal group": "Particularly Vulnerable Tribal Group (PVTG)",

    "dnt": "De-Notified, Nomadic, and Semi-Nomadic (DNT) communities",
    "denotified": "De-Notified, Nomadic, and Semi-Nomadic (DNT) communities",
    "de-notified": "De-Notified, Nomadic, and Semi-Nomadic (DNT) communities",
    "nomadic": "De-Notified, Nomadic, and Semi-Nomadic (DNT) communities",
}

GENDER_LABELS = {
    "female": "Female", "woman": "Female", "women": "Female", "f": "Female",
    "male": "Male", "man": "Male", "men": "Male", "m": "Male",
    "transgender": "Transgender", "trans": "Transgender", "other": "Transgender",
}

RESIDENCE_LABELS = {
    "rural": "Rural", "village": "Rural", "gaon": "Rural",
    "urban": "Urban", "city": "Urban", "town": "Urban",
}

EMPLOYMENT_LABELS = {
    "employed": "Employed",
    "unemployed": "Unemployed",
    "self-employed": "Self-Employed/ Entrepreneur",
    "self_employed": "Self-Employed/ Entrepreneur",
    "entrepreneur": "Self-Employed/ Entrepreneur",
}

MARITAL_LABELS = {
    "never married": "Never Married", "unmarried": "Never Married",
    "single": "Never Married", "married": "Married", "widowed": "Widowed",
    "widow": "Widowed", "divorced": "Divorced", "separated": "Separated",
}

# How each identifier is named to the user when we explain a match.
_FACET_LABELS = {
    "caste": "caste", "gender": "gender", "residence": "residence",
    "occupation": "occupation", "employmentStatus": "employment",
    "maritalStatus": "marital status",
}

# Facets that are a plain Yes requirement — the scheme appears in the index only
# when it demands that condition.
_FLAG_FACETS = {
    "isBpl": "BPL", "disability": "disability", "isStudent": "student",
    "minority": "minority", "isEconomicDistress": "economic distress",
    "isGovEmployee": "government employee",
}


def _label(mapping: dict, value: Optional[str]) -> Optional[str]:
    """Map a machine value to the exact myScheme label, or pass it through.

    Pass-through matters for occupation, where the UI offers the corpus's own
    strings and there is nothing to translate.
    """
    if value is None:
        return None
    return mapping.get(str(value).strip().lower(), value)


# ---------------------------------------------------------------------------
# The matching rules
# ---------------------------------------------------------------------------

def _check_facet(
    scheme_values: Optional[set], user_label: Optional[str], label: str,
    match: DiscoveryMatch,
) -> bool:
    """One set-membership facet, read from the facet index.

    A scheme absent from an identifier is in that identifier's "All" bucket, so
    it restricts nobody — verified by comparing our per-value counts against the
    API's own aggregations. Returns False only on a definite mismatch.
    """
    if not scheme_values:
        return True                       # scheme names no restriction
    if user_label is None:
        match.unknown.append(label)       # scheme restricts, user hasn't said
        return True                       # never exclude on an unanswered question
    if user_label in scheme_values:
        match.matched_on.append(label)
        return True
    match.unmet.append(label)
    return False


def _check_flag_facet(
    scheme_values: Optional[set], user_value: Optional[bool], label: str,
    match: DiscoveryMatch,
) -> bool:
    """A Yes-only requirement: absence from the index means it isn't required."""
    if not scheme_values:
        return True
    if user_value is None:
        match.unknown.append(label)
        return True
    if user_value:
        match.matched_on.append(label)
        return True
    match.unmet.append(label)
    return False


def _check_income(row: sqlite3.Row, income: Optional[float],
                  match: DiscoveryMatch) -> bool:
    """Family income against the scheme's published ceiling.

    ≤, not <. A ceiling of ₹1,00,000 includes someone earning exactly that —
    the same boundary rule the NSFDC engine uses, for the same reason.
    """
    ceiling = row["family_income_max"]
    floor = row["family_income_min"]
    if ceiling is None and floor is None:
        return True
    if income is None:
        match.unknown.append("family income")
        return True
    if ceiling is not None and income > ceiling:
        match.unmet.append("family income")
        return False
    if floor is not None and income < floor:
        match.unmet.append("family income")
        return False
    match.matched_on.append("family income")
    return True


def _check_age(row: sqlite3.Row, age: Optional[int], match: DiscoveryMatch) -> bool:
    low, high = row["age_min"], row["age_max"]
    if low is None and high is None:
        return True
    if age is None:
        match.unknown.append("age")
        return True
    if low is not None and age < low:
        match.unmet.append("age")
        return False
    if high is not None and age > high:
        match.unmet.append("age")
        return False
    match.matched_on.append("age")
    return True


# ---------------------------------------------------------------------------
# Relevance
# ---------------------------------------------------------------------------

# Facets that signal a scheme is *targeted* at a marginalised group. A scheme
# naming these and matching the user should outrank a generic national one.
_TARGETING = {"caste", "BPL", "disability", "minority", "occupation",
              "economic distress"}


def score(match: DiscoveryMatch, facets: Facets) -> float:
    """Deterministic and explainable in one line.

    Targeted matches count triple, a state-specific match for the user's own
    state counts once, and every criterion the user hasn't answered costs two —
    so incomplete profiles surface the schemes we are most sure about.
    """
    targeted = sum(3 for m in match.matched_on if m in _TARGETING)
    local = 1 if (match.state and facets.state and match.state == facets.state) else 0
    penalty = 2 * len(match.unknown)
    return float(targeted + local + len(match.matched_on) - penalty)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _wanted_values(facets: Facets) -> tuple[dict, dict]:
    """The person's answers, in the corpus's exact vocabulary."""
    wanted = {
        "caste": _label(CASTE_LABELS, facets.caste),
        "gender": _label(GENDER_LABELS, facets.gender),
        "residence": _label(RESIDENCE_LABELS, facets.residence),
        "occupation": _label({}, facets.occupation),
        "employmentStatus": _label(EMPLOYMENT_LABELS, facets.employment_status),
        "maritalStatus": _label(MARITAL_LABELS, facets.marital_status),
    }
    flags = {
        "isBpl": facets.is_bpl, "disability": facets.disability,
        "isStudent": facets.is_student, "minority": facets.minority,
        "isEconomicDistress": facets.is_economic_distress,
        "isGovEmployee": facets.is_gov_employee,
    }
    return wanted, flags


def _row_to_match(row: sqlite3.Row) -> DiscoveryMatch:
    return DiscoveryMatch(
        scheme_uid=f"MYS:{row['slug']}",
        slug=row["slug"],
        name=row["name"],
        strength=MatchStrength.LIKELY,
        level=row["level"],
        state=row["state"],
        categories=_json_list(row["categories"]),
        brief=row["brief"],
        eligibility_md=row["eligibility_md"] if "eligibility_md" in row.keys() else None,
        source_url=MYSCHEME_URL.format(slug=row["slug"]),
    )


def discover(
    facets: Facets,
    limit: int = 40,
    include_not_matched: bool = True,
    corpus_path: Path = CORPUS_PATH,
) -> DiscoveryResult:
    """Every scheme this person plausibly qualifies for, ranked."""
    result = DiscoveryResult()
    conn = open_corpus(corpus_path)
    if conn is None:
        result.corpus_available = False
        return result

    try:
        rows = conn.execute(
            """SELECT s.slug, s.name, s.level, s.state, s.categories, s.brief,
                      s.eligibility_md,
                      e.family_income_min, e.family_income_max,
                      e.age_min, e.age_max
               FROM schemes s
               LEFT JOIN scheme_eligibility e ON e.slug = s.slug"""
        ).fetchall()
        index = _load_facet_index(conn)
    finally:
        conn.close()

    result.total_considered = len(rows)

    # Translate once, not 4,736 times.
    wanted, flags = _wanted_values(facets)

    for row in rows:
        if facets.categories:
            cats = {c.lower() for c in _json_list(row["categories"])}
            if not cats & {c.lower() for c in facets.categories}:
                continue

        match = _row_to_match(row)
        scheme_facets = index.get(row["slug"], {})

        checks = [
            _check_facet(scheme_facets.get(ident), user_label,
                         _FACET_LABELS[ident], match)
            for ident, user_label in wanted.items()
        ]
        checks += [
            _check_flag_facet(scheme_facets.get(ident), user_value,
                              _FLAG_FACETS[ident], match)
            for ident, user_value in flags.items()
        ]
        checks += [
            _check_income(row, facets.family_income, match),
            _check_age(row, facets.age, match),
        ]

        # A state-specific scheme only serves its own state.
        if row["state"] and facets.state and row["state"].strip().lower() not in ("all", ""):
            if row["state"].strip().lower() != facets.state.strip().lower():
                match.unmet.append("state")
                checks.append(False)
            else:
                match.matched_on.append("state")

        if all(checks):
            match.strength = MatchStrength.CHECK if match.unknown else MatchStrength.LIKELY
            match.relevance = score(match, facets)
            result.matches.append(match)
        elif include_not_matched:
            match.strength = MatchStrength.NOT_MATCHED
            result.not_matched.append(match)

    result.total_matched = len(result.matches)
    result.total_not_matched = len(result.not_matched)
    result.total_targeted = sum(
        1 for m in result.matches
        if any(reason in _TARGETING for reason in m.matched_on)
    )
    result.strength_counts = {
        "LIKELY": sum(1 for m in result.matches
                      if m.strength is MatchStrength.LIKELY),
        "CHECK": sum(1 for m in result.matches
                     if m.strength is MatchStrength.CHECK),
    }

    result.matches.sort(key=lambda m: (-m.relevance, m.name))
    result.matches = result.matches[:limit]
    result.not_matched = result.not_matched[:10]
    return result


def evaluate_scheme(
    slug: str,
    facets: Facets,
    corpus_path: Path = CORPUS_PATH,
) -> Optional[DiscoveryMatch]:
    """One named scheme, checked criterion by criterion.

    `discover` answers "what might I get?"; this answers "do I qualify for this
    particular one, and which condition is the problem?" — which is the question
    someone asks once they have a scheme name in hand, and the one a counter
    will turn them away over.

    Same rules as everywhere else: a criterion the person has not answered is
    reported as unknown, never as a failure.
    """
    conn = open_corpus(corpus_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            """SELECT s.slug, s.name, s.level, s.state, s.categories, s.brief,
                      s.eligibility_md,
                      e.family_income_min, e.family_income_max,
                      e.age_min, e.age_max
               FROM schemes s
               LEFT JOIN scheme_eligibility e ON e.slug = s.slug
               WHERE s.slug = ?""",
            (slug,),
        ).fetchone()
        if row is None:
            return None
        index = _load_facet_index(conn)
    finally:
        conn.close()

    match = _row_to_match(row)
    scheme_facets = index.get(slug, {})
    wanted, flags = _wanted_values(facets)

    checks = [
        _check_facet(scheme_facets.get(ident), value, _FACET_LABELS[ident], match)
        for ident, value in wanted.items()
    ]
    checks += [
        _check_flag_facet(scheme_facets.get(ident), value, _FLAG_FACETS[ident], match)
        for ident, value in flags.items()
    ]
    checks += [
        _check_income(row, facets.family_income, match),
        _check_age(row, facets.age, match),
    ]
    if row["state"] and facets.state and row["state"].strip().lower() not in ("all", ""):
        if row["state"].strip().lower() != facets.state.strip().lower():
            match.unmet.append("state")
            checks.append(False)
        else:
            match.matched_on.append("state")

    if all(checks):
        match.strength = MatchStrength.CHECK if match.unknown else MatchStrength.LIKELY
    else:
        match.strength = MatchStrength.NOT_MATCHED
    match.relevance = score(match, facets)
    return match


def discover_with_credit(
    facets: Facets,
    profile: Optional[UserProfile] = None,
    limit: int = 40,
    corpus_path: Path = CORPUS_PATH,
) -> DiscoveryResult:
    """Discovery plus the NSFDC credit schemes, which carry a real verdict.

    NSFDC results are inserted at the top with `ELIGIBLE`, because for those five
    every published rule genuinely is evaluated. Everything else stays LIKELY.
    """
    result = discover(facets, limit=limit, corpus_path=corpus_path)
    if profile is None:
        return result

    eligibility = evaluate_eligibility(profile)
    deep: list[DiscoveryMatch] = []
    for m in eligibility.matches:
        deep.append(DiscoveryMatch(
            scheme_uid=f"NSFDC:{m.scheme_id}",
            slug=m.scheme_id.lower().replace("_", "-"),
            name=m.name,
            strength=MatchStrength.ELIGIBLE,
            level="Central",
            categories=["Business & Entrepreneurship"],
            brief=m.why_eligible,
            eligibility_md=m.why_eligible,
            source_url="https://nsfdc.nic.in/scheme",
            depth="DEEP",
            matched_on=["caste", "family income"],
            relevance=1000.0,     # deep, verified schemes always lead
        ))
    result.matches = deep + result.matches
    result.total_matched += len(deep)
    result.total_targeted += len(deep)
    result.strength_counts["ELIGIBLE"] = len(deep)
    return result
