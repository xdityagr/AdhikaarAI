"""What the results page will actually print, per language."""
import re
import sys
import pathlib

sys.path.insert(0, r"C:\Users\Aditya\Projects\AdhikaarAI")
from tests.test_locales import _entries                       # noqa: E402

L = pathlib.Path(r"C:\Users\Aditya\Projects\AdhikaarAI\web\lib\i18n")
vocab = (L / "vocabulary.ts").read_text(encoding="utf-8")
block = vocab[vocab.index("export const FACET_LABELS"):]


def facet(lang: str, name: str) -> str:
    m = re.search(r'\n  "?' + re.escape(name) + r'"?: \{(.*?)\n  \},',
                  block, re.S)
    if not m:
        return name
    got = re.search(lang + r':\s*"([^"]+)"', m.group(1))
    return got.group(1) if got else name


CASES = [
    ("results.notMatchedOn", ["gender"]),
    ("results.notMatchedOn", ["age"]),
    ("results.notMatchedOn", ["caste"]),
    ("results.matchedOn", ["gender", "age", "state"]),
    ("results.stillToCheck", ["occupation"]),
]

for lang in ("hi", "ta", "bn", "mr", "ur"):
    strings = _entries(lang)
    print(f"--- {lang} ---")
    for key, facets in CASES:
        joined = ", ".join(facet(lang, f) for f in facets)
        print("   ", strings[key].replace("{facets}", joined))
    print()
