"""
Backfill the documents checklist and FAQs that the first ingest missed.

Both were silently absent for all 4,736 schemes because of two bugs that the
ingest's `except Exception: pass` hid completely:

  1. It called the sub-resource endpoints with `scheme_id` — the Elasticsearch
     document id from the search index (`LBezF5gB5uF80_MGGY81`). Those routes
     want the record's Mongo `_id` (`628727c27d5de378dc7acfe9`), and answer
     anything else with "Invalid Scheme Id".
  2. It then read `documentsRequired`; the field is `documents_required`.

Either alone returns nothing. Together they return nothing in a way that looks
exactly like "this scheme has no documents listed", which is why 4,736 empty
columns never looked wrong.

The documents matter more than almost anything else we hold. Someone travelling
to a government office without the right papers is sent home and, often enough,
does not come back — so "bring these five things" is the single most useful
sentence this product can produce.

Resumable and rate-limited. Safe to stop and re-run; it skips what it has.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.corpus.myscheme import API_BASE, API_KEY, USER_AGENT   # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")

DB = Path("data/schemes.db")

# myScheme publishes no rate limit, so this is our own restraint rather than
# theirs: about 1.5 requests a second, with an identifying User-Agent.
DELAY = 0.65


def rich_text_to_markdown(nodes) -> str:
    """myScheme returns Slate-style rich text, not markdown.

    Only the shapes that actually appear are handled — ordered and unordered
    lists, list items, paragraphs and plain text. Anything unrecognised
    contributes its text and nothing else, which degrades to a readable line
    rather than to a crash inside a backfill that has already run for an hour.
    """
    out: list[str] = []

    def walk(node, bullet: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, bullet)
            return
        if not isinstance(node, dict):
            return

        kind = node.get("type")
        if kind in ("ul_list", "ol_list"):
            marker = "-" if kind == "ul_list" else "1."
            for child in node.get("children") or []:
                walk(child, marker)
            out.append("")
            return
        if kind == "list_item":
            text = "".join(_text(c) for c in node.get("children") or []).strip()
            if text:
                out.append(f"{bullet or '-'} {text}")
            return
        if kind == "paragraph":
            text = "".join(_text(c) for c in node.get("children") or []).strip()
            if text:
                out.append(text)
                out.append("")
            return

        walk(node.get("children") or [], bullet)

    def _text(node) -> str:
        if isinstance(node, str):
            return node
        if not isinstance(node, dict):
            return ""
        if "text" in node:
            body = node.get("text") or ""
            return f"**{body}**" if node.get("bold") else body
        return "".join(_text(c) for c in node.get("children") or [])

    walk(nodes)
    return "\n".join(out).strip()


def ensure_columns(con: sqlite3.Connection) -> None:
    """`mongo_id` is remembered so a re-run costs one request, not two."""
    columns = {c[1] for c in con.execute("PRAGMA table_info(schemes)")}
    if "mongo_id" not in columns:
        con.execute("ALTER TABLE schemes ADD COLUMN mongo_id TEXT")
        con.commit()
        logger.info("Added schemes.mongo_id")


def fetch(client: httpx.Client, url: str, params: dict) -> dict | None:
    for attempt in (1, 2, 3):
        try:
            response = client.get(url, params=params)
        except Exception as exc:                              # noqa: BLE001
            logger.debug("network error (%s), retry %d", exc, attempt)
            time.sleep(2 * attempt)
            continue

        if response.status_code == 429:
            time.sleep(5 * attempt)
            continue
        if response.status_code != 200:
            return None

        payload = response.json()
        # The API answers 200 with a Failure envelope; that is not success.
        if payload.get("status") != "Success":
            return None
        return payload.get("data")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after this many schemes (0 = all)")
    args = parser.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ensure_columns(con)

    rows = con.execute(
        """SELECT slug, mongo_id FROM schemes
           WHERE documents_md IS NULL OR length(documents_md) < 10
           ORDER BY slug"""
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    total = len(rows)
    logger.info("%d schemes still without documents", total)

    headers = {"x-api-key": API_KEY, "User-Agent": USER_AGENT}
    done = docs_found = faqs_found = 0

    with httpx.Client(timeout=30, headers=headers) as client:
        for row in rows:
            slug = row["slug"]
            mongo_id = row["mongo_id"]

            if not mongo_id:
                detail = fetch(client, f"{API_BASE}/schemes/v6/public/schemes",
                               {"slug": slug, "lang": "en"})
                time.sleep(DELAY)
                mongo_id = (detail or {}).get("_id")
                if not mongo_id:
                    logger.debug("no _id for %s", slug)
                    done += 1
                    continue
                con.execute("UPDATE schemes SET mongo_id = ? WHERE slug = ?",
                            (mongo_id, slug))

            documents_md = None
            data = fetch(client, f"{API_BASE}/schemes/v6/public/schemes/{mongo_id}/documents",
                         {"lang": "en"})
            time.sleep(DELAY)
            if data:
                nodes = (data.get("en") or {}).get("documents_required")
                if nodes:
                    documents_md = rich_text_to_markdown(nodes) or None

            faqs_json = None
            data = fetch(client, f"{API_BASE}/schemes/v6/public/schemes/{mongo_id}/faqs",
                         {"lang": "en"})
            time.sleep(DELAY)
            if data:
                items = (data.get("en") or {}).get("faqs") or []
                pairs = [
                    {"question": i.get("question"),
                     "answer": (i.get("answer_md")
                                or rich_text_to_markdown(i.get("answer") or []))}
                    for i in items if isinstance(i, dict) and i.get("question")
                ]
                if pairs:
                    faqs_json = json.dumps(pairs, ensure_ascii=False)

            sets, params = [], []
            if documents_md:
                sets.append("documents_md = ?")
                params.append(documents_md)
                docs_found += 1
            if faqs_json:
                sets.append("faqs = ?")
                params.append(faqs_json)
                faqs_found += 1
            if sets:
                params.append(slug)
                con.execute(f"UPDATE schemes SET {', '.join(sets)} WHERE slug = ?",
                            params)

            done += 1
            if done % 25 == 0:
                con.commit()
                logger.info("%d/%d — documents %d, faqs %d",
                            done, total, docs_found, faqs_found)

    con.commit()
    con.close()
    logger.info("Finished. %d scanned, %d with documents, %d with FAQs",
                done, docs_found, faqs_found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
