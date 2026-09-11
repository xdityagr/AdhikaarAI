"""
Browsing the scheme corpus — search, filter, and read one scheme.

`src/discovery.py` answers "what do I qualify for?". This answers "what exists?",
which is a different and equally necessary question: a person who does not yet
trust us with their caste and income should still be able to look around, and a
field worker needs to look up a scheme by name.

Everything here is read-only over the SQLite corpus the ingest builds. No network
call at request time — if myScheme goes down, this keeps working.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.discovery import CORPUS_PATH, MYSCHEME_URL, open_corpus

logger = logging.getLogger(__name__)

PAGE_SIZE = 24


def _json_list(raw: Any) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


@dataclass
class SchemeCard:
    """The shape the browse grid renders."""
    slug: str
    name: str
    short_title: Optional[str] = None
    level: Optional[str] = None
    state: Optional[str] = None
    ministry: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    brief: Optional[str] = None
    source_url: str = ""
    has_detail: bool = False


@dataclass
class SchemePage:
    items: list[SchemeCard] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = PAGE_SIZE
    corpus_available: bool = True


def _card(row: sqlite3.Row) -> SchemeCard:
    keys = row.keys()
    return SchemeCard(
        slug=row["slug"],
        name=row["name"],
        short_title=row["short_title"] if "short_title" in keys else None,
        level=row["level"],
        state=row["state"],
        ministry=row["ministry"] if "ministry" in keys else None,
        categories=_json_list(row["categories"]),
        tags=_json_list(row["tags"]) if "tags" in keys else [],
        brief=row["brief"],
        source_url=MYSCHEME_URL.format(slug=row["slug"]),
        has_detail=bool(row["details_md"]) if "details_md" in keys else False,
    )


# ---------------------------------------------------------------------------
# Search and browse
# ---------------------------------------------------------------------------

def _fts_query(text: str) -> str:
    """Turn typed words into a safe FTS5 prefix query.

    Users type names, not query syntax, so every FTS5 operator character is
    stripped rather than escaped — a stray quote must never become a 500. Each
    surviving word gets a `*` so "sil" finds "Silai".
    """
    words = [w for w in "".join(
        c if c.isalnum() or c.isspace() else " " for c in text
    ).split() if w]
    return " ".join(f'"{w}"*' for w in words)


def search_schemes(
    q: str = "",
    state: Optional[str] = None,
    category: Optional[str] = None,
    level: Optional[str] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    lang: str = "en",
    corpus_path: Path = CORPUS_PATH,
) -> SchemePage:
    """Paged browse with optional full-text search and filters.

    State filtering is inclusive of central schemes — the same "All" rule
    discovery uses. A person in Bihar browsing "Bihar" must still see the
    national schemes they can apply for, or the list lies by omission.

    `lang` swaps in myScheme's OWN translations, which we already hold — about
    4,730 schemes in each of nine languages. Nothing is machine-translated
    here: these are the strings the government publishes, so a scheme name is
    the one a person will see on the official site and hear at a counter.

    Switching the interface to Hindi and leaving 4,736 English scheme names on
    the page is barely a translation at all, and this browse list was doing
    exactly that — the detail page took a `lang` and the list it came from
    never had one.
    """
    result = SchemePage(page=max(1, page), page_size=page_size)
    conn = open_corpus(corpus_path)
    if conn is None:
        result.corpus_available = False
        return result

    where: list[str] = []
    params: list[Any] = []

    if q.strip():
        match = _fts_query(q)
        if match:
            where.append(
                "s.slug IN (SELECT slug FROM schemes_fts WHERE schemes_fts MATCH ?)")
            params.append(match)

    if state:
        where.append("(s.state = ? OR s.state = 'All' OR s.state IS NULL)")
        params.append(state)

    if level:
        where.append("s.level = ?")
        params.append(level)

    if category:
        # categories is a JSON array; LIKE on the serialised form is exact enough
        # because category names are controlled vocabulary from myScheme.
        where.append("s.categories LIKE ?")
        params.append(f'%"{category}"%')

    clause = (" WHERE " + " AND ".join(where)) if where else ""

    # COALESCE per field, not per row: a scheme translated in name but not in
    # brief shows the translated name and the English brief, rather than
    # falling back wholesale to English or — worse — showing a blank.
    translated = lang and lang != "en"
    name_col = "COALESCE(NULLIF(i.name, ''), s.name)" if translated else "s.name"
    brief_col = "COALESCE(NULLIF(i.brief, ''), s.brief)" if translated else "s.brief"
    join = " LEFT JOIN scheme_i18n i ON i.slug = s.slug AND i.lang = ?" if translated else ""
    join_params = [lang] if translated else []

    try:
        result.total = conn.execute(
            f"SELECT COUNT(*) FROM schemes s{clause}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT s.slug, {name_col} AS name, s.short_title, s.level,
                       s.state, s.ministry, s.categories, s.tags,
                       {brief_col} AS brief, s.details_md
                FROM schemes s{join}{clause}
                ORDER BY name
                LIMIT ? OFFSET ?""",
            [*join_params, *params, page_size, (result.page - 1) * page_size],
        ).fetchall()
    except sqlite3.OperationalError as exc:
        # A malformed FTS query or a corpus mid-rebuild degrades to empty, never
        # to a stack trace in front of a user.
        logger.warning("Catalogue query failed: %s", exc)
        conn.close()
        return result
    finally:
        conn.close()

    result.items = [_card(r) for r in rows]
    return result


def get_scheme(slug: str, lang: str = "en",
               corpus_path: Path = CORPUS_PATH) -> Optional[dict]:
    """One scheme in full, with its official translation when we have one.

    Translated fields overlay the English record field by field, so a partially
    translated scheme shows Hindi where Hindi exists and English elsewhere —
    better than an all-or-nothing switch that would blank the page.
    """
    conn = open_corpus(corpus_path)
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT * FROM schemes WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None

        scheme = dict(row)
        for key in ("categories", "tags"):
            scheme[key] = _json_list(scheme.get(key))
        scheme["faqs"] = _json_list(scheme.get("faqs"))
        scheme["source_url"] = MYSCHEME_URL.format(slug=slug)

        if lang != "en":
            tr = conn.execute(
                "SELECT * FROM scheme_i18n WHERE slug = ? AND lang = ?",
                (slug, lang)).fetchone()
            if tr is not None:
                for key in ("name", "brief", "benefits_md", "eligibility_md",
                            "application_md"):
                    if tr[key]:
                        scheme[key] = tr[key]
                scheme["language"] = lang

        elig = conn.execute(
            "SELECT * FROM scheme_eligibility WHERE slug = ?", (slug,)).fetchone()
        if elig is not None:
            structured = dict(elig)
            for key in ("caste", "gender", "residence", "occupation", "education",
                        "beneficiary_states", "age_bands"):
                structured[key] = _json_list(structured.get(key))
            structured.pop("eligibility_json", None)   # the raw blob is for audit, not the wire
            scheme["structured_eligibility"] = structured
    finally:
        conn.close()
    return scheme


# ---------------------------------------------------------------------------
# Filter vocabulary
# ---------------------------------------------------------------------------

def catalog_meta(corpus_path: Path = CORPUS_PATH) -> dict:
    """The values the filter UI offers, read from the corpus itself.

    Never hardcoded: myScheme's facet values are exact strings, and a hand-typed
    one that does not match returns zero results with no error — the trap that
    cost us an afternoon during the ingest.
    """
    conn = open_corpus(corpus_path)
    if conn is None:
        return {"corpus_available": False, "total": 0, "categories": [],
                "states": [], "levels": []}
    try:
        total = conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]

        counts: dict[str, int] = {}
        for (raw,) in conn.execute(
                "SELECT categories FROM schemes WHERE categories IS NOT NULL"):
            for c in _json_list(raw):
                counts[c] = counts.get(c, 0) + 1

        states = [
            {"name": name, "count": n}
            for name, n in conn.execute(
                """SELECT state, COUNT(*) FROM schemes
                   WHERE state IS NOT NULL AND state != ''
                   GROUP BY state ORDER BY state""")
        ]
        levels = [
            {"name": name, "count": n}
            for name, n in conn.execute(
                """SELECT level, COUNT(*) FROM schemes
                   WHERE level IS NOT NULL AND level != ''
                   GROUP BY level ORDER BY COUNT(*) DESC""")
        ]
        detailed = conn.execute(
            "SELECT COUNT(*) FROM scheme_eligibility").fetchone()[0]
    finally:
        conn.close()

    return {
        "corpus_available": True,
        "total": total,
        "with_structured_eligibility": detailed,
        "categories": sorted(
            ({"name": k, "count": v} for k, v in counts.items()),
            key=lambda c: -c["count"]),
        "states": states,
        "levels": levels,
    }
