"""
myScheme ingest — the 4,772-scheme national corpus.

The government publishes every central and state welfare scheme through
myscheme.gov.in, and its front end talks to a JSON API that is open in practice.
That gives us housing, pensions, scholarships, health and disability schemes
alongside the NSFDC credit products — which is the difference between a loan
calculator and something a poor household can actually use.

FOUR THINGS ABOUT THIS API THAT WILL COST YOU A DAY IF YOU MISS THEM:

1. **Facet values are full label strings.** The caste value is
   "Scheduled Caste (SC)", not "SC". A wrong value returns `total: 0` with HTTP
   200 and no error at all. So facet values are never hardcoded here — they are
   read from the API's own `facets` block and stored verbatim.

2. **The facets are NOT on the scheme record.** Neither the search hit nor the
   detail response carries caste/gender/isBpl/disability/occupation. The detail
   has only `eligibilityDescription_md`, which is prose. The facets exist ONLY as
   aggregations on the search endpoint. So the only way to know which schemes
   match "caste = Scheduled Caste (SC)" is to ASK the search endpoint for that
   filter and record the slugs that come back. That is what pass 2 does, and it
   is why this module exists rather than a simple detail crawl.

3. **"All" is a real value, and ignoring it inverts the product.** `caste` has an
   `All` bucket of ~4,001 schemes open to everyone. Filtering to SC alone returns
   394 and hides the rest. Matching therefore has to be
   `value ∈ {user_value, "All"}` — but that is a QUERY-time concern
   (`src/discovery.py`); this module just records the truth as published.

4. **Structured eligibility only comes back under a NON-ENGLISH `lang`.**
   `lang=en` returns `eligibilityCriteria` with 2 keys — prose only. `lang=hi`
   returns the same scheme with **24 keys**: caste, gender, age bands,
   familyIncomeAnnual{gte,lte}, isBpl, occupation, residence, beneficiaryState,
   employmentStatus, education... The `value` fields are stable machine strings
   ("sc", "farmer", 100000); only `label` is translated.

   Almost certainly a bug in their API — the English overlay strips to
   translated-only fields, while other overlays leak the base document. We depend
   on it deliberately and defensively: it turns "match 4,772 prose rules" into the
   same numeric/enum matching the NSFDC engine already does. Mitigations, because
   a bug can be fixed: the facet sweep is kept as an INDEPENDENT source that does
   not rely on this, `eligibility_json` is stored verbatim so a built corpus keeps
   working forever, and a test asserts the quirk still holds so a scheduled run
   tells us before a demo does.

Conduct: there is no published ToS for this endpoint, so we behave as guests —
throttled to ~1.5 req/s, an identifying User-Agent, aggressive caching, and the
app never calls it on the request path. Every scheme we show deep-links back to
myscheme.gov.in.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.myscheme.gov.in"

# A browser key, hardcoded in myScheme's own public JS bundle. Not a secret, and
# not ours — it is the key their front end ships to every visitor.
API_KEY = "tYTy5eEhlu9rFjyxuCr7ra7ACp4dv1RH8gWuHTDc"

USER_AGENT = (
    "YojnaSetu/0.2 (+https://github.com/xdityagr/AdhikaarAI; "
    "SIH 2026 PS26092; welfare scheme discovery for NSFDC beneficiaries)"
)

PAGE_SIZE = 100          # the API's hard maximum; larger returns malformed data
THROTTLE_SECONDS = 0.7   # ~1.5 req/s
REQUEST_TIMEOUT = 30.0

LANGUAGES = ("en", "hi", "mr", "bn", "ta")

# Facets worth crawling. Deliberately EXCLUDES beneficiaryState, schemeCategory,
# level, ministry and tags — those already come back on every search hit during
# pass 1, so facet-crawling them would be ~150 wasted pages.
#
# What's left is the personal eligibility that appears nowhere on the record.
MATCHING_FACETS = (
    "gender", "caste", "residence", "minority", "disability", "isBpl",
    "isEconomicDistress", "isGovEmployee", "employmentStatus", "isStudent",
    "occupation", "maritalStatus",
)

# The "open to everyone" value for each facet. A scheme carrying one of these is
# not restricted on that axis, and the buckets are enormous — caste=All alone is
# 4,001 schemes, 41 pages, to learn nothing.
#
# So we crawl only the RESTRICTIVE values and treat absence as the default. That
# takes the facet pass from ~350 pages to ~70, and it is also the more honest
# model: the index records restrictions, not permissions.
FACET_DEFAULTS = {
    "gender": "All",
    "caste": "All",
    "residence": "Both",
    "minority": "No",
    "disability": "No",
    "isBpl": "No",
    "isEconomicDistress": "No",
    "isGovEmployee": "No",
    "employmentStatus": "All",
    "isStudent": "No",
    "occupation": "All",
    "maritalStatus": "All",
}

from src.paths import CATALOGUE_DB as DB_PATH

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS schemes (
        slug TEXT PRIMARY KEY,
        scheme_id TEXT,
        name TEXT NOT NULL,
        short_title TEXT,
        level TEXT,
        state TEXT,
        ministry TEXT,
        categories TEXT,          -- JSON array
        tags TEXT,                -- JSON array
        brief TEXT,
        details_md TEXT,
        benefits_md TEXT,
        eligibility_md TEXT,
        exclusions_md TEXT,
        application_md TEXT,
        documents_md TEXT,
        faqs TEXT,                -- JSON array of {question, answer}
        official_url TEXT,
        depth TEXT NOT NULL DEFAULT 'DISCOVERY',   -- FULL only for NSFDC credit
        source TEXT NOT NULL DEFAULT 'myscheme',
        fetched_at TEXT,
        -- When this scheme FIRST appeared in the corpus. Written on insert and
        -- never touched again, which is the whole point: `fetched_at` moves on
        -- every re-crawl, so it can say when we last looked but never when
        -- something arrived. "A scheme launched and you now qualify" is a
        -- question only this column can answer.
        first_seen TEXT,
        -- Hash of the structured eligibility, so a widened criterion is
        -- detectable without keeping an old copy of the corpus to diff against.
        eligibility_hash TEXT
    )
    """,
    # Structured eligibility, harvested from the lang=hi overlay. This is what
    # makes deterministic matching over 4,772 schemes possible.
    """
    CREATE TABLE IF NOT EXISTS scheme_eligibility (
        slug TEXT PRIMARY KEY,
        caste TEXT,                  -- JSON array of machine values: ["sc","st"]
        gender TEXT,                 -- JSON array
        residence TEXT,              -- JSON array
        occupation TEXT,             -- JSON array
        education TEXT,              -- JSON array
        beneficiary_states TEXT,     -- JSON array of numeric state ids
        employment_status TEXT,
        nationality TEXT,
        is_bpl TEXT,                 -- "Yes" | "No" | NULL (NULL = unspecified)
        is_student TEXT,
        is_gov_employee TEXT,
        is_economic_distress TEXT,
        nri TEXT,
        minority TEXT,
        disability TEXT,
        family_income_min REAL,
        family_income_max REAL,
        individual_income_max REAL,
        parent_income_max REAL,
        age_min INTEGER,             -- coarse envelope across all bands
        age_max INTEGER,
        age_bands TEXT,              -- JSON array of {gte,lte,category}
        eligibility_json TEXT,       -- the whole object, verbatim, forever
        fetched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scheme_i18n (
        slug TEXT NOT NULL,
        lang TEXT NOT NULL,
        name TEXT,
        brief TEXT,
        benefits_md TEXT,
        eligibility_md TEXT,
        application_md TEXT,
        fetched_at TEXT,
        PRIMARY KEY (slug, lang)
    )
    """,
    # The facet index — built by asking the API, because it is not on the record.
    """
    CREATE TABLE IF NOT EXISTS scheme_facets (
        slug TEXT NOT NULL,
        identifier TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY (slug, identifier, value)
    )
    """,
    # What the API itself reported, so we can prove our index is complete.
    """
    CREATE TABLE IF NOT EXISTS facet_totals (
        identifier TEXT NOT NULL,
        value TEXT NOT NULL,
        api_count INTEGER NOT NULL,
        indexed_at TEXT,
        PRIMARY KEY (identifier, value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_state (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_facets_lookup ON scheme_facets(identifier, value)",
    "CREATE INDEX IF NOT EXISTS idx_facets_slug ON scheme_facets(slug)",
    "CREATE INDEX IF NOT EXISTS idx_schemes_level ON schemes(level)",
    "CREATE INDEX IF NOT EXISTS idx_schemes_state ON schemes(state)",
    # Standalone FTS5, NOT external-content. An external-content table keyed on
    # `schemes.rowid` corrupted the database on rebuild ("database disk image is
    # malformed") because the content table is rewritten by upserts. A standalone
    # index costs a little space and cannot desynchronise.
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS schemes_fts USING fts5(
        slug UNINDEXED, name, short_title, brief, tags,
        tokenize='unicode61 remove_diacritics 2'
    )
    """,
]


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

@dataclass
class FacetValue:
    identifier: str
    value: str
    count: int


@dataclass
class IngestReport:
    ok: bool = True
    schemes_indexed: int = 0
    facet_values: int = 0
    facet_rows: int = 0
    details_fetched: int = 0
    translations: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def note(self, message: str) -> None:
        logger.warning(message)
        self.errors.append(message)
        self.ok = False


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


#: Columns added after the first corpus was already built. `CREATE TABLE IF NOT
#: EXISTS` does nothing to a table that exists, so a corpus ingested before these
#: were declared would silently lack them and every query against them would
#: throw. Additive only — this cannot rename, retype or drop, and it is not the
#: beginning of a migration system.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "schemes": [("first_seen", "TEXT"), ("eligibility_hash", "TEXT")],
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                logger.info("Added %s.%s to an existing corpus", table, name)


def init_db(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA:
        conn.execute(statement)
    _ensure_columns(conn)
    # Backfill `first_seen` for a corpus built before the column existed. The
    # honest value is when we first fetched the scheme, not now — dating 4,736
    # existing schemes to today would announce the entire corpus as "new" on the
    # first alert run and message every user about every scheme they qualify for.
    conn.execute(
        "UPDATE schemes SET first_seen = fetched_at "
        "WHERE first_seen IS NULL AND fetched_at IS NOT NULL"
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class MySchemeClient:
    """Throttled client. One instance per ingest run."""

    def __init__(self, throttle: float = THROTTLE_SECONDS):
        self._client = httpx.Client(
            headers={"x-api-key": API_KEY, "User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        self._throttle = throttle
        self._last_call = 0.0

    def __enter__(self) -> "MySchemeClient":
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._throttle:
            time.sleep(self._throttle - elapsed)
        self._last_call = time.monotonic()

    def search(
        self,
        facets: Optional[list[dict]] = None,
        keyword: str = "",
        offset: int = 0,
        size: int = PAGE_SIZE,
        lang: str = "en",
    ) -> dict:
        """One page of the search endpoint. Returns the `data` block."""
        self._wait()
        response = self._client.get(
            f"{API_BASE}/search/v6/schemes",
            params={
                "lang": lang,
                "q": json.dumps(facets or []),
                "keyword": keyword,
                "sort": "",
                "from": offset,
                "size": size,
            },
        )
        response.raise_for_status()
        return response.json()["data"]

    def detail(self, slug: str, lang: str = "en") -> Optional[dict]:
        self._wait()
        response = self._client.get(
            f"{API_BASE}/schemes/v6/public/schemes",
            params={"slug": slug, "lang": lang},
        )
        if response.status_code != 200:
            return None
        return response.json().get("data")

    def sub_resource(self, scheme_id: str, name: str, lang: str = "en") -> Optional[dict]:
        """`documents` or `faqs` for one scheme."""
        self._wait()
        response = self._client.get(
            f"{API_BASE}/schemes/v6/public/schemes/{scheme_id}/{name}",
            params={"lang": lang},
        )
        if response.status_code != 200:
            return None
        return response.json().get("data")


# ---------------------------------------------------------------------------
# Pass 1 — the index
# ---------------------------------------------------------------------------

def read_facets(client: MySchemeClient) -> list[FacetValue]:
    """Read every facet value the API publishes, verbatim.

    Never hardcode these. "Scheduled Caste (SC)" vs "SC" is the difference
    between 394 results and a silent zero.
    """
    data = client.search(size=1)
    out: list[FacetValue] = []
    for facet in data.get("facets", []):
        identifier = facet.get("identifier")
        if identifier not in MATCHING_FACETS:
            continue
        for entry in facet.get("entries", []):
            label, count = entry.get("label"), entry.get("count", 0)
            # Range facets (age, disability %) carry numeric labels; they are
            # matched arithmetically, not by membership, so they are skipped here.
            if label is None or not isinstance(label, str):
                continue
            # Skip the "open to everyone" bucket — absence means the default.
            if label == FACET_DEFAULTS.get(identifier):
                continue
            out.append(FacetValue(identifier, label, count))
    return out


def crawl_index(client: MySchemeClient, conn: sqlite3.Connection,
                report: IngestReport) -> list[str]:
    """Every scheme's summary row. ~48 requests."""
    slugs: list[str] = []
    offset = 0
    total = None

    while True:
        try:
            data = client.search(offset=offset, size=PAGE_SIZE)
        except Exception as exc:
            report.note(f"Index page at offset {offset} failed: {exc}")
            break

        if total is None:
            total = data["summary"]["total"]
            logger.info("myScheme reports %d schemes", total)

        items = data["hits"]["items"]
        if not items:
            break

        rows = []
        for item in items:
            f = item.get("fields", {})
            slug = f.get("slug")
            if not slug:
                continue
            slugs.append(slug)
            states = f.get("beneficiaryState") or []
            rows.append((
                slug, item.get("id"), f.get("schemeName", ""), f.get("schemeShortTitle"),
                f.get("level"), states[0] if states else None,
                f.get("nodalMinistryName"),
                json.dumps(f.get("schemeCategory") or []),
                json.dumps(f.get("tags") or []),
                f.get("briefDescription"),
                f"https://www.myscheme.gov.in/schemes/{slug}",
                _now(),
                _now(),          # first_seen — on insert only; see below
            ))

        # `first_seen` is deliberately absent from the DO UPDATE SET. That
        # omission is the feature: re-crawling a scheme we already hold must not
        # reset the date it arrived, or every scheme becomes "new" on every
        # ingest and the change-alert layer messages everybody about everything.
        conn.executemany(
            """
            INSERT INTO schemes (slug, scheme_id, name, short_title, level, state,
                                 ministry, categories, tags, brief, official_url,
                                 fetched_at, first_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET
                scheme_id=excluded.scheme_id, name=excluded.name,
                short_title=excluded.short_title, level=excluded.level,
                state=excluded.state, ministry=excluded.ministry,
                categories=excluded.categories, tags=excluded.tags,
                brief=excluded.brief, official_url=excluded.official_url,
                fetched_at=excluded.fetched_at
            """,
            rows,
        )
        conn.commit()

        offset += PAGE_SIZE
        if total is not None and offset >= total:
            break

    report.schemes_indexed = len(slugs)
    return slugs


# ---------------------------------------------------------------------------
# Pass 2 — the facet index (the reason this module exists)
# ---------------------------------------------------------------------------

def crawl_facets(client: MySchemeClient, conn: sqlite3.Connection,
                 report: IngestReport,
                 only: Optional[Iterable[str]] = None) -> None:
    """Ask the API which schemes carry each facet value, and record it.

    This is the only way to get structured eligibility: the facets are
    aggregations on the search endpoint, not fields on the scheme record.
    """
    facet_values = read_facets(client)
    if only:
        wanted = set(only)
        facet_values = [f for f in facet_values if f.identifier in wanted]

    report.facet_values = len(facet_values)
    logger.info("Indexing %d facet values", len(facet_values))

    for fv in facet_values:
        if fv.count == 0:
            continue
        collected: list[tuple[str, str, str]] = []
        offset = 0
        query = [{"identifier": fv.identifier, "value": fv.value}]

        while offset < fv.count:
            try:
                data = client.search(facets=query, offset=offset, size=PAGE_SIZE)
            except Exception as exc:
                report.note(f"Facet {fv.identifier}={fv.value!r} page {offset} failed: {exc}")
                break
            items = data["hits"]["items"]
            if not items:
                break
            for item in items:
                slug = item.get("fields", {}).get("slug")
                if slug:
                    collected.append((slug, fv.identifier, fv.value))
            offset += PAGE_SIZE

        conn.executemany(
            "INSERT OR IGNORE INTO scheme_facets (slug, identifier, value) VALUES (?,?,?)",
            collected,
        )
        conn.execute(
            """INSERT INTO facet_totals (identifier, value, api_count, indexed_at)
               VALUES (?,?,?,?)
               ON CONFLICT(identifier, value) DO UPDATE SET
                 api_count=excluded.api_count, indexed_at=excluded.indexed_at""",
            (fv.identifier, fv.value, fv.count, _now()),
        )
        conn.commit()
        report.facet_rows += len(collected)

        if len(collected) != fv.count:
            report.note(
                f"Facet {fv.identifier}={fv.value!r}: indexed {len(collected)} "
                f"but the API reports {fv.count}"
            )


# ---------------------------------------------------------------------------
# Pass 3 — detail and translations
# ---------------------------------------------------------------------------

def _md(block: Optional[dict], key: str) -> Optional[str]:
    """Prefer the Markdown twin over the Slate AST — it is clean and chunkable."""
    if not isinstance(block, dict):
        return None
    return block.get(f"{key}_md") or None


def _values(block: Any) -> list:
    """Pull the stable machine `value` out of myScheme's {value,label} objects.

    ALWAYS the value, never the label — labels are translated, so a Hindi crawl
    would otherwise store "अनुसूचित जाति (एससी)" where English stored "sc".
    """
    if not isinstance(block, list):
        return []
    out = []
    for entry in block:
        if isinstance(entry, dict):
            v = entry.get("value")
            if v is not None:
                out.append(v)
        elif entry is not None:
            out.append(entry)
    return out


def _flag(value: Any) -> Optional[str]:
    """Yes/No flags. None means UNSPECIFIED, which is NOT the same as "No"."""
    if value in (None, "", []):
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value).strip()
    return text or None


def _money(block: Any, key: str) -> Optional[float]:
    if not isinstance(block, dict):
        return None
    v = block.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def parse_structured_eligibility(criteria: dict) -> dict:
    """Flatten the 24-field lang=hi eligibility object into columns.

    Absence is preserved as NULL throughout. `isBpl: null` means the scheme does
    not say, which is NOT "No" — treating it as No would wrongly exclude people,
    and wrong exclusion is the worst failure this product can have.
    """
    bands = criteria.get("age") or []
    band_rows = [
        {"gte": b.get("gte"), "lte": b.get("lte"), "category": b.get("category")}
        for b in bands if isinstance(b, dict)
    ]
    lows = [b["gte"] for b in band_rows if isinstance(b["gte"], int)]
    highs = [b["lte"] for b in band_rows if isinstance(b["lte"], int)]

    return {
        "caste": json.dumps(_values(criteria.get("caste")), ensure_ascii=False),
        "gender": json.dumps(_values(criteria.get("gender")), ensure_ascii=False),
        "residence": json.dumps(_values(criteria.get("residence")), ensure_ascii=False),
        "occupation": json.dumps(_values(criteria.get("occupation")), ensure_ascii=False),
        "education": json.dumps(_values(criteria.get("education")), ensure_ascii=False),
        "beneficiary_states": json.dumps(_values(criteria.get("beneficiaryState")), ensure_ascii=False),
        "employment_status": _flag(criteria.get("employmentStatus")),
        "nationality": _flag(criteria.get("nationality")),
        "is_bpl": _flag(criteria.get("isBpl")),
        "is_student": _flag(criteria.get("isStudent")),
        "is_gov_employee": _flag(criteria.get("isGovEmployee")),
        "is_economic_distress": _flag(criteria.get("isEconomicDistress")),
        "nri": _flag(criteria.get("nri")),
        "minority": _flag(criteria.get("minority")),
        "disability": _flag(criteria.get("disability")),
        "family_income_min": _money(criteria.get("familyIncomeAnnual"), "gte"),
        "family_income_max": _money(criteria.get("familyIncomeAnnual"), "lte"),
        "individual_income_max": _money(criteria.get("individualIncomeAnnual"), "lte"),
        "parent_income_max": _money(criteria.get("parentIncomeAnnual"), "lte"),
        "age_min": min(lows) if lows else None,
        "age_max": max(highs) if highs else None,
        "age_bands": json.dumps(band_rows, ensure_ascii=False) if band_rows else None,
        "eligibility_json": json.dumps(criteria, ensure_ascii=False),
    }


def eligibility_hash(parsed: dict) -> str:
    """A stable fingerprint of the structured eligibility.

    Used to notice that a criterion moved — an income ceiling raised, an age band
    widened — without keeping a second copy of a 285 MB corpus to diff against.
    Sorted keys and a canonical separator so the hash tracks the VALUES and not
    the order a dict happened to be built in; `fetched_at` is excluded, or every
    re-crawl would look like a change.
    """
    canonical = json.dumps(
        {k: parsed[k] for k in sorted(parsed) if k != "fetched_at"},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def store_eligibility(conn: sqlite3.Connection, slug: str, parsed: dict) -> None:
    cols = list(parsed.keys())
    conn.execute(
        f"""INSERT INTO scheme_eligibility (slug, {', '.join(cols)}, fetched_at)
            VALUES (?{', ?' * len(cols)}, ?)
            ON CONFLICT(slug) DO UPDATE SET
              {', '.join(f'{c}=excluded.{c}' for c in cols)}, fetched_at=excluded.fetched_at""",
        [slug] + [parsed[c] for c in cols] + [_now()],
    )
    # Kept on `schemes` rather than `scheme_eligibility` so the alert diff is one
    # table scan over the same row it already reads for `first_seen`.
    conn.execute(
        "UPDATE schemes SET eligibility_hash = ? WHERE slug = ?",
        (eligibility_hash(parsed), slug),
    )


def crawl_details(client: MySchemeClient, conn: sqlite3.Connection,
                  report: IngestReport, slugs: Optional[list[str]] = None,
                  limit: Optional[int] = None,
                  fetch_sub_resources: bool = False) -> None:
    """Full content for each scheme.

    Two requests per scheme by default: lang=en for English prose, lang=hi for
    the structured eligibility that only the non-English overlay returns.

    Documents and FAQs are opt-in because they double the crawl to four
    requests per scheme — 4,772 schemes is 5 hours instead of 2.5. They are
    Plane B content, not needed to decide eligibility, so they can be fetched
    lazily when a scheme is actually viewed.
    """
    if slugs is None:
        rows = conn.execute(
            "SELECT slug FROM schemes WHERE details_md IS NULL ORDER BY slug"
        ).fetchall()
        slugs = [r["slug"] for r in rows]
    if limit:
        slugs = slugs[:limit]

    for slug in slugs:
        try:
            data = client.detail(slug)
        except Exception as exc:
            report.note(f"Detail for {slug} failed: {exc}")
            continue
        if not data:
            continue

        en = data.get("en", {})
        content = en.get("schemeContent", {})
        eligibility = en.get("eligibilityCriteria", {})
        scheme_id = data.get("_id")

        # The structured eligibility only exists under a non-English overlay.
        # One extra request per scheme buys deterministic matching instead of
        # prose matching, which is the whole reason this is affordable at all.
        try:
            hi = client.detail(slug, lang="hi") or {}
            criteria = (hi.get("hi") or {}).get("eligibilityCriteria") or {}
            if isinstance(criteria, dict) and len(criteria) > 2:
                store_eligibility(conn, slug, parse_structured_eligibility(criteria))
        except Exception as exc:
            report.note(f"Structured eligibility for {slug} failed: {exc}")

        processes = en.get("applicationProcess") or []
        application_md = "\n\n".join(
            f"**{p.get('mode', '')}**\n\n{p.get('process_md', '')}".strip()
            for p in processes if isinstance(p, dict)
        ) or None

        documents_md = None
        faqs_json = None
        if scheme_id and fetch_sub_resources:
            try:
                docs = client.sub_resource(scheme_id, "documents")
                documents_md = _md((docs or {}).get("en", {}), "documentsRequired")
            except Exception:
                pass
            try:
                faqs = client.sub_resource(scheme_id, "faqs")
                items = ((faqs or {}).get("en", {}) or {}).get("faqs") or []
                faqs_json = json.dumps([
                    {"question": i.get("question"), "answer": i.get("answer_md") or i.get("answer")}
                    for i in items if isinstance(i, dict)
                ], ensure_ascii=False) if items else None
            except Exception:
                pass

        conn.execute(
            """UPDATE schemes SET details_md=?, benefits_md=?, eligibility_md=?,
                   exclusions_md=?, application_md=?, documents_md=?, faqs=?,
                   scheme_id=COALESCE(scheme_id, ?), fetched_at=?
               WHERE slug=?""",
            (
                _md(content, "detailedDescription"),
                _md(content, "benefits"),
                _md(eligibility, "eligibilityDescription"),
                _md(content, "exclusions"),
                application_md,
                documents_md,
                faqs_json,
                scheme_id,
                _now(),
                slug,
            ),
        )
        conn.commit()
        report.details_fetched += 1


def store_translation(conn: sqlite3.Connection, slug: str, lang: str,
                      data: Optional[dict]) -> bool:
    """Write one translated scheme. False when the API returned nothing for it.

    Extracted so the bulk crawl and any gap-filling retry write through exactly
    the same code — two copies of an upsert is two places for the columns to
    drift apart.
    """
    block = (data or {}).get(lang)
    if not block:
        return False

    basic = block.get("basicDetails", {})
    content = block.get("schemeContent", {})
    eligibility = block.get("eligibilityCriteria", {})
    conn.execute(
        """INSERT INTO scheme_i18n (slug, lang, name, brief, benefits_md,
                                    eligibility_md, application_md, fetched_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(slug, lang) DO UPDATE SET
             name=excluded.name, brief=excluded.brief,
             benefits_md=excluded.benefits_md,
             eligibility_md=excluded.eligibility_md,
             fetched_at=excluded.fetched_at""",
        (
            slug, lang, basic.get("schemeName"),
            content.get("briefDescription"),
            _md(content, "benefits"),
            _md(eligibility, "eligibilityDescription"),
            None, _now(),
        ),
    )
    conn.commit()
    return True


def missing_translations(conn: sqlite3.Connection, lang: str) -> list[str]:
    """Slugs with no row for this language yet."""
    return [
        row["slug"]
        for row in conn.execute(
            """SELECT s.slug FROM schemes s
               LEFT JOIN scheme_i18n i ON i.slug = s.slug AND i.lang = ?
               WHERE i.slug IS NULL ORDER BY s.slug""",
            (lang,),
        )
    ]


def crawl_translations(client: MySchemeClient, conn: sqlite3.Connection,
                       report: IngestReport, langs: Iterable[str] = ("hi",),
                       limit: Optional[int] = None,
                       skip_existing: bool = True,
                       attempts: int = 2) -> None:
    """Official government translations — better than machine-translating.

    Resumable by default: a language already stored is not fetched again, so a
    run interrupted at 78% picks up where it stopped instead of spending an hour
    re-downloading what it has. Pass `skip_existing=False` to refresh.

    Retries once by default, because the failure this most often hits is an
    empty response body under rate pressure rather than a missing translation —
    treating that as "no translation exists" would quietly leave gaps.
    """
    for lang in langs:
        slugs = (missing_translations(conn, lang) if skip_existing
                 else [r["slug"] for r in
                       conn.execute("SELECT slug FROM schemes ORDER BY slug")])
        if limit:
            slugs = slugs[:limit]
        logger.info("Translations %s: %d to fetch", lang, len(slugs))

        for slug in slugs:
            for attempt in range(attempts):
                try:
                    if store_translation(conn, slug, lang, client.detail(slug, lang=lang)):
                        report.translations += 1
                    break
                except Exception as exc:                       # noqa: BLE001
                    if attempt == attempts - 1:
                        report.note(f"Translation {lang} for {slug} failed: {exc}")
                    else:
                        time.sleep(2)


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Rebuild the search index from scratch. Standalone table — see SCHEMA."""
    conn.execute("DELETE FROM schemes_fts")
    conn.execute(
        """INSERT INTO schemes_fts (slug, name, short_title, brief, tags)
           SELECT slug, name, COALESCE(short_title,''), COALESCE(brief,''),
                  COALESCE(tags,'') FROM schemes"""
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_ingest(db_path: Path = DB_PATH, detail_limit: Optional[int] = None,
               translation_langs: Iterable[str] = (),
               translation_limit: Optional[int] = None) -> IngestReport:
    """Full ingest. Resumable — re-running skips schemes already detailed."""
    report = IngestReport(started_at=_now())
    conn = connect(db_path)
    init_db(conn)
    try:
        with MySchemeClient() as client:
            crawl_index(client, conn, report)
            crawl_facets(client, conn, report)
            crawl_details(client, conn, report, limit=detail_limit)
            if translation_langs:
                crawl_translations(client, conn, report,
                                   langs=translation_langs, limit=translation_limit)
        rebuild_fts(conn)
    finally:
        conn.close()
    report.finished_at = _now()
    return report
