"""
Corpus ingest — NSFDC published performance data.

This is what turns the prudential router from "real rule, mocked data" into
"real rule, real published data". NSFDC publishes state-wise allocation vs
actual disbursement as Excel, current to 31 July 2026, and the %AGE column in
that file IS the cumulative utilisation figure the SCA prudential norm is
assessed against.

Three rules that shape everything here:

1. NEVER CONSTRUCT A DOWNLOAD URL. NSFDC's filenames are rotating date-hashes
   (20260812_112204_V7yI6L.xlsx) served from two different path prefixes. They
   change whenever a file is updated. URLs are discovered by parsing hrefs off
   the listing page, every time.

2. NEVER BLOCK A USER ON A GOVERNMENT WEBSITE. NSKFDC refused connection outright
   during research. Refresh runs on a schedule, off the request path, and on any
   failure the last good data stays in place with its age visible.

3. PREFER PUBLISHED FILES TO SCRAPED HTML. A site redesign breaks a CSS selector;
   it does not break a spreadsheet. The Excel and PDF files are also the format
   the publisher intended for reuse.

Heavy dependencies (pandas, pdfplumber) are imported lazily inside the functions
that need them, so importing this module from the web process stays cheap.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

PERFORMANCE_DATA_PAGE = "https://nsfdc.nic.in/performance-data"
CHANNEL_PARTNERS_PAGE = "https://nsfdc.nic.in/our-channel-partners"

# An honest User-Agent identifying the project and its purpose. Required by
# OpenStreetMap's tile policy and simply good conduct against a ministry's site —
# this is public data, fetched monthly, and we should be identifiable while we do it.
USER_AGENT = (
    "YojnaSetu/0.1 (+https://github.com/xdityagr/AdhikaarAI; "
    "SIH 2026 PS26092; NSFDC scheme matching for beneficiaries)"
)

REQUEST_TIMEOUT = 45.0


@dataclass
class DiscoveredFile:
    """A downloadable file found on a listing page."""
    title: str
    url: str
    extension: str


@dataclass
class StateUtilisation:
    """One state's allocation vs actual disbursement for one financial year.

    `utilisation_pct` is what the SCA prudential norm is assessed against:
    fresh releases require 100% cumulative utilisation of prior disbursements.
    """
    state: str
    financial_year: str
    allocation_lakh: float
    actual_lakh: float
    utilisation_pct: float
    source_url: str = ""
    fetched_at: str = ""

    @property
    def meets_sca_utilisation_norm(self) -> bool:
        return self.utilisation_pct >= 100.0


@dataclass
class IngestResult:
    """Outcome of one refresh. Never raises at the caller — check `ok`."""
    ok: bool
    rows: list[StateUtilisation] = field(default_factory=list)
    files_seen: list[DiscoveredFile] = field(default_factory=list)
    error: str = ""
    fetched_at: str = ""


# ---------------------------------------------------------------------------
# Discovery and download
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def discover_files(
    page_url: str,
    extensions: tuple[str, ...] = (".xlsx", ".xls", ".pdf"),
    client: Optional[httpx.Client] = None,
) -> list[DiscoveredFile]:
    """Find downloadable files by parsing hrefs off a listing page.

    Deliberately parses rather than constructs — see rule 1 in the module docstring.
    The link text is used as the title, since NSFDC labels each dataset in the
    anchor or its surrounding row.
    """
    from selectolax.parser import HTMLParser

    owns_client = client is None
    client = client or _client()
    try:
        response = client.get(page_url)
        response.raise_for_status()
        tree = HTMLParser(response.text)

        found: list[DiscoveredFile] = []
        seen: set[str] = set()
        for node in tree.css("a[href]"):
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            lower = href.lower()
            ext = next((e for e in extensions if lower.endswith(e)), None)
            if ext is None:
                continue
            absolute = urljoin(page_url, href)
            if absolute in seen:
                continue
            seen.add(absolute)

            title = " ".join((node.text() or "").split()) or node.attributes.get("title", "")
            found.append(DiscoveredFile(title=title, url=absolute, extension=ext))
        return found
    finally:
        if owns_client:
            client.close()


def download(url: str, client: Optional[httpx.Client] = None, max_retries: int = 3) -> bytes:
    """Download a file with retries. Raises on final failure — callers catch."""
    owns_client = client is None
    client = client or _client()
    try:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = client.get(url)
                response.raise_for_status()
                return response.content
            except Exception as exc:  # network, HTTP, timeout
                last_error = exc
                logger.warning("Download attempt %d/%d failed for %s: %s",
                               attempt + 1, max_retries, url, exc)
        raise RuntimeError(f"Failed to download {url}: {last_error}")
    finally:
        if owns_client:
            client.close()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FY_PATTERN = re.compile(r"(\d{4})\s*-\s*(\d{2,4})")

# Rows that are aggregates or notes, not states.
_NON_STATE_ROWS = {"total", "grand total", "all india", "nan", ""}


def _clean_number(value) -> Optional[float]:
    """Coerce a spreadsheet cell to a float, or None if it isn't one."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in ("nan", "-", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_state_utilisation(
    xlsx_bytes: bytes,
    source_url: str = "",
) -> list[StateUtilisation]:
    """Parse NSFDC's state-wise allocation-vs-actuals workbook.

    Layout (as published 2026-08-12):
        row 0    title
        row 1    "(RS. IN LAKH)"
        row 2    financial-year labels, one per 3-column group
        row 3    ALLOCATION | ACTUALS | %AGE, repeating
        row 4+   one row per state: Srno | State | then the triplets

    The header rows are located by content rather than by index, so a cosmetic
    change to the file (an extra title row, say) doesn't silently misalign every
    column — it either still works or it returns nothing, and returning nothing
    is caught by the caller.
    """
    import pandas as pd
    import io as _io

    frame = pd.read_excel(_io.BytesIO(xlsx_bytes), header=None)

    # The sheet holds SEVERAL stacked tables, each with its own header block and
    # its own 5-year range (2022-23 onwards in the first, 2017-18 in the next,
    # and so on). Parsing one header and then reading to end-of-file applies the
    # wrong column mapping to every later block — which produced 135 "states"
    # per year and utilisation figures in the thousands of percent.
    #
    # So: find every header block, and read each one only to the end of its own
    # table.
    header_rows: list[int] = []
    for idx in range(len(frame)):
        cells = {str(v).strip().upper() for v in frame.iloc[idx].tolist()}
        # Match whole CELLS, not a row substring: the title row reads
        # "DISBURSEMENT : NOTIONAL ALLOCATION VS ACTUALS" and contains both words.
        if "ALLOCATION" in cells and ("ACTUALS" in cells or "ACTUAL" in cells):
            header_rows.append(idx)
    if not header_rows:
        raise ValueError("Could not locate any ALLOCATION/ACTUALS header row")

    fetched_at = datetime.now(timezone.utc).isoformat()
    # (state, financial_year) -> row. Later blocks win, so the most recently
    # published figure for a year survives if two blocks overlap.
    collected: dict[tuple[str, str], StateUtilisation] = {}

    for block_no, sub_header_idx in enumerate(header_rows):
        fy_row = frame.iloc[max(0, sub_header_idx - 1)].tolist()
        sub_row = frame.iloc[sub_header_idx].tolist()

        # Pair each ALLOCATION column with the financial year above it. The FY
        # header is a merged cell, so it appears once and the next two read NaN.
        groups: list[tuple[str, int, int, int]] = []
        current_fy = ""
        for col, label in enumerate(sub_row):
            fy_cell = str(fy_row[col]) if col < len(fy_row) else ""
            match = _FY_PATTERN.search(fy_cell)
            if match:
                year_end = match.group(2)
                if len(year_end) == 2:
                    year_end = match.group(1)[:2] + year_end
                current_fy = f"{match.group(1)}-{year_end}"
            if str(label).strip().upper() == "ALLOCATION" and current_fy:
                groups.append((current_fy, col, col + 1, col + 2))
        if not groups:
            continue

        state_col = 1
        for col, value in enumerate(fy_row):
            if str(value).strip().upper() == "STATE":
                state_col = col
                break

        # Read to the end of THIS block: stop at a Total row, or at the next
        # header block, or after two consecutive blank rows.
        end = header_rows[block_no + 1] if block_no + 1 < len(header_rows) else len(frame)
        blanks = 0
        for idx in range(sub_header_idx + 1, end):
            record = frame.iloc[idx].tolist()
            state = str(record[state_col]).strip() if state_col < len(record) else ""
            normalised = state.lower().rstrip(" :")

            if normalised in _NON_STATE_ROWS:
                if normalised in ("total", "grand total", "all india"):
                    break          # end of this table
                blanks += 1
                if blanks >= 3:
                    break
                continue
            blanks = 0

            for financial_year, alloc_col, actual_col, pct_col in groups:
                allocation = _clean_number(record[alloc_col]) if alloc_col < len(record) else None
                actual = _clean_number(record[actual_col]) if actual_col < len(record) else None
                pct = _clean_number(record[pct_col]) if pct_col < len(record) else None
                if allocation is None and actual is None:
                    continue
                allocation = allocation or 0.0
                actual = actual or 0.0
                # Prefer the published percentage; derive only when absent.
                derived = (actual / allocation * 100.0) if allocation else 0.0
                if pct is None:
                    pct = derived
                elif allocation and abs(pct - derived) > 1.0:
                    # The published %AGE disagrees with actual/allocation. That
                    # means the columns are misaligned — the workbook stacks
                    # several tables with different layouts, and a silent
                    # misread here would put a wrong utilisation figure behind a
                    # claim we make out loud. Drop the row rather than guess.
                    logger.warning(
                        "Discarding %s %s: published %.2f%% but actual/allocation is %.2f%%",
                        state, financial_year, pct, derived,
                    )
                    continue

                collected[(state, financial_year)] = StateUtilisation(
                    state=state,
                    financial_year=financial_year,
                    allocation_lakh=allocation,
                    actual_lakh=actual,
                    utilisation_pct=round(pct, 2),
                    source_url=source_url,
                    fetched_at=fetched_at,
                )

    return list(collected.values())


def _pick_allocation_workbook(files: list[DiscoveredFile]) -> Optional[DiscoveredFile]:
    """Choose the allocation-vs-actuals workbook from a discovered file list."""
    spreadsheets = [f for f in files if f.extension in (".xlsx", ".xls")]
    for wanted in ("notional allocation", "allocation"):
        for candidate in spreadsheets:
            if wanted in candidate.title.lower():
                return candidate
    return spreadsheets[0] if spreadsheets else None


def fetch_state_utilisation(page_url: str = PERFORMANCE_DATA_PAGE) -> IngestResult:
    """Discover, download and parse the state-wise utilisation data.

    Never raises. On any failure the result carries ok=False and an error, and
    the caller keeps whatever data it already had — a government site being down
    must never surface to a beneficiary mid-conversation.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        with _client() as client:
            files = discover_files(page_url, client=client)
            if not files:
                return IngestResult(ok=False, error="No downloadable files found on the page",
                                    fetched_at=fetched_at)

            workbook = _pick_allocation_workbook(files)
            if workbook is None:
                return IngestResult(ok=False, files_seen=files,
                                    error="No spreadsheet found among discovered files",
                                    fetched_at=fetched_at)

            payload = download(workbook.url, client=client)
            rows = parse_state_utilisation(payload, source_url=workbook.url)

        logger.info("Ingested %d state-year utilisation rows from %s", len(rows), workbook.url)
        return IngestResult(ok=True, rows=rows, files_seen=files, fetched_at=fetched_at)

    except Exception as exc:
        logger.warning("Utilisation ingest failed (keeping existing data): %s", exc)
        return IngestResult(ok=False, error=f"{type(exc).__name__}: {exc}", fetched_at=fetched_at)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

async def store_state_utilisation(db, rows: list[StateUtilisation]) -> int:
    """Upsert utilisation rows into partner_performance. Returns rows written."""
    if not rows:
        return 0
    written = 0
    for row in rows:
        await db.execute(
            """
            INSERT INTO partner_performance
                (scope, scope_key, period, allocation, disbursed,
                 cumulative_utilization, beneficiaries, confidence, source_url, fetched_at)
            VALUES ('STATE', ?, ?, ?, ?, ?, NULL, 'OFFICIAL', ?, ?)
            ON CONFLICT(scope, scope_key, period) DO UPDATE SET
                allocation = excluded.allocation,
                disbursed = excluded.disbursed,
                cumulative_utilization = excluded.cumulative_utilization,
                confidence = excluded.confidence,
                source_url = excluded.source_url,
                fetched_at = excluded.fetched_at
            """,
            (row.state, row.financial_year, row.allocation_lakh, row.actual_lakh,
             row.utilisation_pct, row.source_url, row.fetched_at),
        )
        written += 1
    await db.commit()
    return written


async def get_state_utilisation(db, state: str, period: Optional[str] = None) -> Optional[dict]:
    """Latest published utilisation for a state, or for one financial year."""
    if period:
        cursor = await db.execute(
            "SELECT * FROM partner_performance WHERE scope='STATE' AND scope_key=? AND period=?",
            (state, period),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM partner_performance WHERE scope='STATE' AND scope_key=? "
            "ORDER BY period DESC LIMIT 1",
            (state,),
        )
    row = await cursor.fetchone()
    return dict(row) if row else None
