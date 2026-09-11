"""What the interface will actually print, per language.

Key coverage is not evidence of a translation. `tests/test_locales.py` proves
every locale holds every key and that the placeholders survive; it cannot tell
you that the finished sentence reads like something a person would say. Every
defect so far has been in that gap:

    मेल नहीं खाता gender      the template translated, the value did not
    लिंग ची अट                concatenation cannot inflect a Marathi noun
    جنس, عمر                  Arabic script takes the Arabic comma

So this substitutes realistic values and prints the result. It is meant to be
read, not asserted on — run it and look at the lines.

    python scripts/render.py                    # the five review languages
    python scripts/render.py hi mr              # just these
    python scripts/render.py --all              # all thirteen

It also reports which interpolating keys have no case here yet, because a key
nobody has put a value into is a key nobody has read.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_locales import _codes, _entries                     # noqa: E402

I18N = ROOT / "web" / "lib" / "i18n"
VOCAB = (I18N / "vocabulary.ts").read_text(encoding="utf-8")

#: The five the handoff asks for: Devanagari, Tamil, Bengali, a language whose
#: nouns inflect, and the one written right-to-left in Arabic script.
REVIEW = ("hi", "ta", "bn", "mr", "ur")


def _table(name: str) -> str:
    """One `Vocabulary` object out of vocabulary.ts, as source text."""
    start = VOCAB.index(f"export const {name}")
    return VOCAB[start:VOCAB.index("};", start)]


def _separator(lang: str) -> str:
    """The list separator the app uses — Urdu's is the Arabic comma.

    Read out of vocabulary.ts rather than repeated here. A harness that joins
    with ", " in every language cannot show you the defect it exists to find:
    this file used to do exactly that, and printed a Latin comma in the Urdu
    line while `facetList` was already producing the right one.
    """
    block = VOCAB[VOCAB.index("const SEPARATOR"):]
    block = block[:block.index(";")]
    found = re.search(lang + r':\s*"([^"]+)"', block)
    return found.group(1) if found else ", "


def label(table: str, lang: str, name: str) -> str:
    """One entry from a vocabulary table, falling back to the name itself."""
    entry = re.search(r'\n  "?' + re.escape(name) + r'"?: \{(.*?)\n  \},',
                      _table(table), re.S)
    if not entry:
        return name
    found = re.search(lang + r':\s*"([^"]+)"', entry.group(1))
    return found.group(1) if found else name


def facets(lang: str, names: list[str]) -> str:
    return _separator(lang).join(label("FACET_LABELS", lang, n) for n in names)


#: How a value in a case is resolved: a list of facet names, one document label,
#: or another key looked up in the same locale.
RESOLVERS = {
    "facets": lambda lang, arg, strings: facets(lang, arg),
    "document": lambda lang, arg, strings: label("DOCUMENT_LABELS", lang, arg),
    "key": lambda lang, arg, strings: strings[arg],
}


#: Each case is a key and the values to put in it, built per language so that
#: anything interpolated is translated too — which is the whole point. A value
#: given as `("key", "some.other.key")` resolves through the same locale.
CASES: list[tuple[str, dict]] = [
    # The reasons a scheme matched, or did not. The three defects above all
    # lived here.
    ("results.matchedOn", {"facets": ("facets", ["gender", "age", "state"])}),
    ("results.notMatchedOn", {"facets": ("facets", ["gender"])}),
    ("results.notMatchedOn", {"facets": ("facets", ["caste", "age"])}),
    ("results.stillToCheck", {"facets": ("facets", ["occupation"])}),

    # Counts that change the noun they are counting. One and twelve, because a
    # language with a dual or a classifier gets this wrong at exactly one.
    ("results.h1.targeted", {"count": 1}),
    ("results.h1.targeted", {"count": 12}),
    ("household.result.targeted", {"count": 1}),
    ("household.result.targeted", {"count": 12}),
    ("household.result.plain", {"count": 1}),
    ("household.result.plain", {"count": 12}),

    # A child and an elderly person, because several of these languages mark
    # the two differently.
    ("household.card.age", {"age": 7}),
    ("household.card.age", {"age": 70}),

    # The timeline. `{stage}` must arrive already translated — the tracker does
    # that, and this proves the sentence reads once it has.
    ("track.stage.usuallyBy", {"days": 30}),
    ("track.preparing.papers", {"count": 3}),
    ("track.card.applied", {"days": 9}),
    ("track.card.ref", {"reference": "NSFDC/2026/114"}),
    ("track.card.mark", {"stage": ("key", "track.stage.docs")}),
    ("track.card.mark", {"stage": ("key", "track.stage.pfms")}),
    ("track.escalate.grievance", {"stage": ("key", "track.stage.sanctioned"),
                                  "next": ("key", "track.stage.pfms")}),

    # The assistant's cards, which were printing English welded onto data.
    ("chat.card.aimed", {"total": "4,736"}),
    ("chat.card.found", {"count": "128"}),
    ("chat.card.matchedOn", {"facets": ("facets", ["caste", "family income"])}),
    ("results.matchedOn", {"facets": ("facets", ["assets", "land"])}),
    ("chat.card.years", {"years": 5}),
    ("chat.card.km", {"km": 12}),
    ("chat.card.compare", {"label": ("key", "chat.cheapest"),
                            "amount": "₹1,34,400",
                            "loan": "₹1,20,000",
                            "saving": "₹14,400"}),
    ("apply.blanksLeft", {"n": 2}),

    # A document name interpolated into a translated sentence. These come from
    # `KNOWN_DOCUMENTS` in src/documents.py as English, and went in raw until
    # `DOCUMENT_LABELS` existed — "यह आपका Aadhaar card लगता है" in Hindi.
    ("documents.ticked", {"name": ("document", "Aadhaar card")}),
    ("documents.ticked", {"name": ("document", "Caste certificate")}),
    ("documents.notOnList", {"name": ("document", "Driving licence")}),
    ("documents.stillMissing", {"count": 5}),

    ("check.matching.targeted", {"count": 41}),
    ("credit.instalment", {"n": 36}),
    ("profile.filled", {"n": 4, "total": 9}),
    ("results.h1.plain", {"count": 12}),
    ("scheme.source.copied", {"date": "12 September 2026"}),
    ("home.lede", {"count": "4,736"}),
    # The endonym, so the offer to switch is readable to the person being
    # offered it — Urdu is named in Urdu, not in the language they are leaving.
    ("lang.suggest", {"language": "اردو"}),
    ("wa.prefill.resume", {"code": "YS-4K2P"}),

    ("schemes.lede", {"count": "4,736"}),
    ("schemes.filter.showAll", {"count": "4,736"}),
    ("results.showing", {"shown": 20, "total": 128}),
    ("results.lede.targeted", {"count": 41}),
    ("results.lede.plain", {"total": "4,736"}),
    ("notfound.back", {"home": ("key", "notfound.home")}),
    ("partners.npa", {"rate": "2.4"}),
    ("home.cats.cta", {"count": "4,736"}),
]


def fill(lang: str, strings: dict[str, str], key: str, values: dict) -> str:
    text = strings[key]
    for name, value in values.items():
        if isinstance(value, tuple):
            kind, arg = value
            value = RESOLVERS[kind](lang, arg, strings)
        text = text.replace("{" + name + "}", str(value))
    return text


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--all" in sys.argv:
        langs = ["en"] + _codes()
    else:
        langs = args or list(REVIEW)

    english = _entries("en")
    missing = sorted({key for key, _ in CASES} - set(english))
    if missing:
        print(f"!! no such key in en.ts: {missing}\n")

    for lang in langs:
        strings = _entries(lang)
        print(f"--- {lang} " + "-" * (68 - len(lang)))
        for key, values in CASES:
            if key in missing:
                continue
            print(f"  {key}")
            print(f"      {fill(lang, strings, key, values)}")
        print()

    # A key that interpolates and has no case above has never been read with a
    # value in it, which is where every one of these defects has come from.
    covered = {key for key, _ in CASES}
    unread = sorted(
        key for key, text in english.items()
        if re.search(r"\{\w+\}", text) and key not in covered)
    if unread:
        print(f"{len(unread)} interpolating key(s) with no case here yet:")
        for key in unread:
            print(f"  {key}  —  {english[key]}")
    else:
        print("Every interpolating key in en.ts has a case here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
