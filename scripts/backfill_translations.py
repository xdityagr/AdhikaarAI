"""
Backfill the translated "how to apply" and "what to carry".

Two of the four things a person acts on were English on every non-English page,
for two different reasons:

  application_md   `store_translation` wrote a literal None into the column. The
                   API had been returning `process_md` in Hindi the whole time
                   and nothing read it.
  documents_md     there was no such column on `scheme_i18n` at all, and the
                   documents live behind a separate sub-resource endpoint —
                   the same one `backfill_documents.py` exists to call.

So a Hindi scheme page gave its name, summary, benefits and eligibility in Hindi
and then, at exactly the point where somebody stops reading and starts doing,
switched to English for the steps and the papers.

Two requests per scheme per language, resumable, and safe to stop. It skips what
it already holds, so an interrupted run picks up where it stopped rather than
spending an hour re-downloading.

    python scripts/backfill_translations.py --langs hi
    python scripts/backfill_translations.py --langs hi,mr,bn,ta --limit 50
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backfill_documents import rich_text_to_markdown        # noqa: E402
from src.corpus.myscheme import (                                    # noqa: E402
    API_BASE,
    API_KEY,
    USER_AGENT,
    init_db,
    store_translation,
)
from src.paths import CATALOGUE_DB                                   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("backfill-translations")

DELAY = 0.65


def fetch(client: httpx.Client, url: str, params: dict) -> dict | None:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as exc:                                        # noqa: BLE001
        logger.debug("%s failed: %s", url, exc)
        return None


def pending(conn: sqlite3.Connection, lang: str) -> list[sqlite3.Row]:
    """Schemes whose translation is missing either of the two fields.

    A row that already has both is skipped entirely — that is what makes this
    safe to re-run, and it is why the first pass of a language is slow and every
    one after it is fast.
    """
    return conn.execute(
        """SELECT s.slug, s.mongo_id,
                  t.application_md AS app, t.documents_md AS docs
           FROM schemes s
           LEFT JOIN scheme_i18n t ON t.slug = s.slug AND t.lang = ?
           WHERE t.slug IS NULL
              OR t.application_md IS NULL OR trim(t.application_md) = ''
              OR t.documents_md IS NULL OR trim(t.documents_md) = ''
           ORDER BY s.slug""",
        (lang,),
    ).fetchall()


def run(db_path: Path, langs: list[str], limit: int) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)

    headers = {"x-api-key": API_KEY, "User-Agent": USER_AGENT}
    with httpx.Client(timeout=30, headers=headers) as client:
        for lang in langs:
            rows = pending(conn, lang)
            if limit:
                rows = rows[:limit]
            logger.info("%s: %d schemes to fill", lang, len(rows))
            steps = docs = 0

            for index, row in enumerate(rows, 1):
                slug = row["slug"]

                # The detail call carries the translated application process,
                # and store_translation writes every translated field from it.
                if not (row["app"] or "").strip():
                    detail = fetch(client, f"{API_BASE}/schemes/v6/public/schemes",
                                   {"slug": slug, "lang": lang})
                    time.sleep(DELAY)
                    if detail and store_translation(conn, slug, lang,
                                                    detail.get("data")):
                        steps += 1

                # Documents are a separate sub-resource, keyed on the Mongo id
                # rather than the slug — the mistake that left the English
                # column empty for 4,736 schemes until it was found.
                if not (row["docs"] or "").strip() and row["mongo_id"]:
                    payload = fetch(
                        client,
                        f"{API_BASE}/schemes/v6/public/schemes/{row['mongo_id']}/documents",
                        {"lang": lang},
                    )
                    time.sleep(DELAY)
                    block = ((payload or {}).get("data") or {})
                    block = block.get(lang) or block
                    nodes = block.get("documents_required")
                    markdown = rich_text_to_markdown(nodes) if nodes else ""
                    if markdown.strip():
                        conn.execute(
                            """INSERT INTO scheme_i18n (slug, lang, documents_md)
                               VALUES (?,?,?)
                               ON CONFLICT(slug, lang) DO UPDATE SET
                                 documents_md=excluded.documents_md""",
                            (slug, lang, markdown),
                        )
                        docs += 1

                if index % 25 == 0:
                    conn.commit()
                    logger.info("%s  %d/%d — steps %d, documents %d",
                                lang, index, len(rows), steps, docs)
            conn.commit()
            logger.info("%s done. steps %d, documents %d", lang, steps, docs)

    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(CATALOGUE_DB))
    parser.add_argument("--langs", default="hi",
                        help="comma-separated, e.g. hi,mr,bn,ta")
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after this many schemes per language")
    args = parser.parse_args()
    langs = [code.strip() for code in args.langs.split(",") if code.strip()]
    return run(Path(args.db), langs, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
