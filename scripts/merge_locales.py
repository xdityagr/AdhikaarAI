"""Insert translations into web/lib/i18n/locales/*.ts.

Writes new keys before the closing brace and REPLACES existing ones in place.
The last version of this script appended after a line that already ended in a
comma and produced `"...",,` in all twelve files; this one builds each line
itself and never splices around punctuation it has not looked at.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[0]
LOCALES = pathlib.Path(
    r"C:\Users\Aditya\Projects\AdhikaarAI\web\lib\i18n\locales")

merged: dict[str, dict[str, str]] = {}
for name in sys.argv[1:]:
    for lang, pairs in json.loads((ROOT / name).read_text(encoding="utf-8")).items():
        merged.setdefault(lang, {}).update(pairs)


def literal(value: str) -> str:
    """A TypeScript double-quoted string. Only " and \\ need escaping; the
    translations are plain text and deliberately use curly quotes so that no
    escaping is needed inside them at all."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


for lang, pairs in sorted(merged.items()):
    path = LOCALES / f"{lang}.ts"
    text = path.read_text(encoding="utf-8")
    added = replaced = 0

    for key, value in pairs.items():
        line = f"  {literal(key)}: {literal(value)},"
        existing = re.compile(
            r'^[ \t]*"' + re.escape(key) + r'"\s*:\s*"(?:[^"\\]|\\.)*"\s*,?[ \t]*$',
            re.M)
        if existing.search(text):
            text = existing.sub(line.rstrip(), text, count=1)
            replaced += 1
        else:
            # Before the final closing brace, which every locale ends with.
            # The entry already there may be the last one and so may have no
            # trailing comma — appending after it without adding one is exactly
            # how the previous run of this script broke all twelve files.
            close = text.rstrip().rfind("}")
            head = text[:close].rstrip()
            if not head.endswith(","):
                head += ","
            text = head + "\n" + line + "\n" + text[close:]
            added += 1

    path.write_text(text, encoding="utf-8")
    print(f"{lang}.ts  +{added} new, {replaced} replaced")
