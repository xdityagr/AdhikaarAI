"""
Populate the asset columns from the eligibility prose.

The sibling of `extract_land.py`, and the half of Phase 3 that was missing:
`land.py`'s docstring mentions assets, which made the job look finished when
only land had been done. Land is one asset among several, and the others sit in
the same prose in the same shape.

Offline and deterministic. It reads `schemes.eligibility_md`, runs
`src.corpus.assets.extract`, and writes what it found into `scheme_eligibility`.
No network, no model, no API key — re-running it on the same corpus produces the
same answer, which is what makes the result something a judge can audit.

Run after an ingest, before publishing a corpus release:

    python scripts/extract_assets.py --report     # look first
    python scripts/extract_assets.py              # then write

**Read the report.** Forty-seven schemes is few enough to check by eye, and this
is exactly the kind of rule that wrongly excludes someone who qualifies: telling
a family living in a kutcha hut that they do not qualify for a housing scheme,
because we read "house" where the scheme wrote "pucca house", is the harm the
whole project is arranged to prevent.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.corpus.assets import extract            # noqa: E402
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

    tally: Counter[str] = Counter()
    carried = flagged = 0

    for row in rows:
        rule = extract(row["eligibility_md"])
        if rule.empty:
            continue
        carried += 1
        flagged += rule.unquantified
        for kind in rule.must_not_own:
            tally[f"must not own {kind}"] += 1
        for kind in rule.must_own:
            tally[f"must own {kind}"] += 1

        bits = []
        if rule.must_not_own:
            bits.append("NOT " + ",".join(sorted(rule.must_not_own)))
        if rule.must_own:
            bits.append("MUST " + ",".join(sorted(rule.must_own)))
        if rule.unquantified:
            bits.append("flagged")
        print(f"  {' | '.join(bits):<34} {row['name'][:38]:<40} "
              f"| {rule.evidence[0][:70] if rule.evidence else ''}")

        if not write:
            continue
        # The eligibility row may not exist yet for a scheme the detail crawl
        # has not reached; an upsert keyed on slug covers both cases.
        conn.execute(
            """INSERT INTO scheme_eligibility
                   (slug, assets_must_not_own, assets_must_own,
                    assets_family_scope, assets_unquantified, assets_evidence)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET
                   assets_must_not_own=excluded.assets_must_not_own,
                   assets_must_own=excluded.assets_must_own,
                   assets_family_scope=excluded.assets_family_scope,
                   assets_unquantified=excluded.assets_unquantified,
                   assets_evidence=excluded.assets_evidence""",
            (row["slug"],
             json.dumps(sorted(rule.must_not_own)),
             json.dumps(sorted(rule.must_own)),
             int(rule.family_scope), int(rule.unquantified),
             json.dumps(rule.evidence, ensure_ascii=False)),
        )

    if write:
        conn.commit()
    conn.close()

    print(f"\n  schemes read      : {len(rows)}")
    print(f"  with an asset rule: {carried}")
    for label, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"    {label:<26} {n}")
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
