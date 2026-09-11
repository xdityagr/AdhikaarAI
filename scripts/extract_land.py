"""
Populate the land columns from the eligibility prose.

Offline and deterministic: it reads `schemes.eligibility_md`, runs
`src.corpus.land.extract`, and writes what it found into `scheme_eligibility`.
No network, no model, no API key — re-running it on the same corpus produces the
same numbers, which is what makes the result something a judge can audit.

Run after an ingest, before publishing a corpus release:

    python scripts/extract_land.py --report      # look first
    python scripts/extract_land.py               # then write

`--report` prints every ceiling it would write with the sentence it came from.
Read that list. Eleven schemes is few enough to check by eye, and a land ceiling
is exactly the kind of rule that wrongly excludes someone who qualifies.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.corpus.land import extract              # noqa: E402
from src.corpus.myscheme import init_db          # noqa: E402
from src.paths import CATALOGUE_DB               # noqa: E402


def run(db_path: Path, write: bool) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)                                # adds the columns if missing

    rows = conn.execute(
        "SELECT slug, name, eligibility_md FROM schemes "
        "WHERE eligibility_md IS NOT NULL AND trim(eligibility_md) <> ''"
    ).fetchall()

    ceilings = minimums = landless = flagged = 0
    for row in rows:
        rule = extract(row["eligibility_md"])
        if rule.empty:
            continue
        ceilings += rule.max_acres is not None
        minimums += rule.min_acres is not None
        landless += rule.landless_required
        flagged += rule.unquantified and rule.max_acres is None and rule.min_acres is None

        if rule.max_acres is not None:
            print(f"  MAX {rule.max_acres:7.2f} ac  {row['name'][:44]:<46} "
                  f"| {rule.evidence[0][:80] if rule.evidence else ''}")

        if not write:
            continue
        # The eligibility row may not exist yet for a scheme the detail crawl
        # has not reached; an upsert keyed on slug covers both cases.
        conn.execute(
            """INSERT INTO scheme_eligibility
                   (slug, land_min_acres, land_max_acres,
                    land_landless_required, land_unquantified, land_evidence)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET
                   land_min_acres=excluded.land_min_acres,
                   land_max_acres=excluded.land_max_acres,
                   land_landless_required=excluded.land_landless_required,
                   land_unquantified=excluded.land_unquantified,
                   land_evidence=excluded.land_evidence""",
            (row["slug"], rule.min_acres, rule.max_acres,
             int(rule.landless_required), int(rule.unquantified),
             json.dumps(rule.evidence, ensure_ascii=False)),
        )

    if write:
        conn.commit()
    conn.close()

    print(f"\n  schemes read      : {len(rows)}")
    print(f"  ceilings          : {ceilings}")
    print(f"  minimums          : {minimums}")
    print(f"  landless required : {landless}")
    print(f"  flagged, unread   : {flagged}")
    print("  " + ("WRITTEN" if write else "report only — nothing written"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(CATALOGUE_DB))
    parser.add_argument("--report", action="store_true",
                        help="print what would be written, change nothing")
    args = parser.parse_args()
    return run(Path(args.db), write=not args.report)


if __name__ == "__main__":
    raise SystemExit(main())
