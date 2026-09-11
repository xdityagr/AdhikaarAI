"""Does the step parser survive this language?

`src/application.py` splits a scheme's "how to apply" into steps, and it was
written against the shape Hindi comes back in. Another language can arrive
punctuated differently, and the two ways that shows up are both measurable:

  collapsed   the whole section parsed as one or two blobs, so the page shows a
              wall of text where English shows a numbered list
  disagrees   a different number of steps than the English of the same scheme,
              which means one of the two is wrong

Hindi went from 4273 collapsed to 1689, and from agreeing with English on 10%
of schemes to 29%, when `_STEP_LABEL` was widened to fit it. Run this after
backfilling a language and compare.

    python scripts/sweep.py ur              # one language
    python scripts/sweep.py hi ur mr        # several
    python scripts/sweep.py                 # every language in the corpus

If a language splits badly the likely cause is its word for "Step" not matching
`_STEP_LABEL` in src/application.py. Widen it with a test — the place is
tests/test_application_and_handoff.py::TestStepsSurviveTranslation, and
`test_a_number_in_prose_is_not_mistaken_for_a_step` is the guard against
over-splitting.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.application import parse_list                             # noqa: E402
from src.paths import CATALOGUE_DB                                 # noqa: E402

LIMIT = 15


def languages(conn: sqlite3.Connection) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT lang, COUNT(*) FROM scheme_i18n "
        "WHERE application_md IS NOT NULL AND trim(application_md) != '' "
        "GROUP BY lang ORDER BY 2 DESC")]


def report(conn: sqlite3.Connection, lang: str, english: dict[str, str]) -> None:
    rows = conn.execute(
        "SELECT slug, application_md FROM scheme_i18n "
        "WHERE lang = ? AND application_md IS NOT NULL "
        "AND trim(application_md) != ''", (lang,)).fetchall()
    if not rows:
        print(f"{lang}: nothing backfilled yet\n")
        return

    collapsed = shared = agree = 0
    worst: list[tuple[str, int, int]] = []
    for slug, md in rows:
        steps = parse_list(md, LIMIT)
        if len(steps) <= 2:
            collapsed += 1
        if slug in english:
            shared += 1
            want = len(parse_list(english[slug], LIMIT))
            if len(steps) == want:
                agree += 1
            elif len(worst) < 5 and want - len(steps) >= 3:
                worst.append((slug, want, len(steps)))

    total = len(rows)
    print(f"{lang}: {total} schemes with a translated apply section")
    print(f"  collapsed to <=2 items : {collapsed} "
          f"({100 * collapsed / total:.0f}%)")
    print(f"  same step count as English : {agree}/{shared} "
          f"({100 * agree / max(shared, 1):.0f}%)")
    for slug, want, got in worst:
        print(f"    {slug}: English {want} steps, {lang} {got}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("langs", nargs="*", help="language codes; default all")
    parser.add_argument("--db", default=str(CATALOGUE_DB))
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    english = dict(conn.execute(
        "SELECT slug, application_md FROM schemes "
        "WHERE application_md IS NOT NULL AND trim(application_md) != ''"))
    print(f"English: {len(english)} schemes with an apply section, "
          f"{sum(1 for md in english.values() if len(parse_list(md, LIMIT)) <= 2)}"
          f" of them collapsed\n")

    for lang in (args.langs or languages(conn)):
        report(conn, lang, english)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
