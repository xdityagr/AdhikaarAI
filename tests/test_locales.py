"""
Every locale carries every string.

This exists because of a specific failure. New interface strings were added to
`en.ts` only — the apply card, the document checklist, the location errors — and
`t()` falls back to English, so nothing broke, nothing warned, and a person
reading the site in Hindi saw "Papers", "What to carry" and "5 still to find" in
the middle of Hindi prose. Graceful fallback is right for a half-finished
translation and wrong as a way to find out one exists.

The frontend has no test runner, so this is checked from the Python suite, which
does run. Parsing TypeScript with a regex is ordinarily a poor idea; here the
file is a flat object literal of `"key": "value"` pairs written by hand, and the
alternative is the check not existing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

LOCALES = Path(__file__).resolve().parents[1] / "web" / "lib" / "i18n" / "locales"

#: `t()` resolves a missing key to English, so English is the one that must be
#: complete. Everything else is measured against it.
REFERENCE = "en"

_ENTRY = re.compile(r'"([a-zA-Z0-9_.]+)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _entries(code: str) -> dict[str, str]:
    path = LOCALES / f"{code}.ts"
    return dict(_ENTRY.findall(path.read_text(encoding="utf-8")))


def _codes() -> list[str]:
    return sorted(p.stem for p in LOCALES.glob("*.ts") if p.stem != REFERENCE)


@pytest.mark.parametrize("code", _codes())
def test_locale_has_every_string(code):
    """A locale that has fallen behind names the keys it is missing."""
    reference = _entries(REFERENCE)
    missing = sorted(set(reference) - set(_entries(code)))
    assert not missing, (
        f"{code}.ts is missing {len(missing)} string(s), which will render in "
        f"English inside {code} prose: {missing[:12]}"
    )


@pytest.mark.parametrize("code", _codes())
def test_placeholders_survive_translation(code):
    """`{count}` and `{name}` are substituted by `t()`, not translated.

    A translator who renders `{count}` as `{गिनती}` produces a sentence with a
    literal brace in it where a number should be — which looks like a bug in the
    software rather than in the string, and is the kind of thing nobody notices
    until it is in front of someone.
    """
    reference = _entries(REFERENCE)
    translated = _entries(code)
    for key, english in reference.items():
        if key not in translated:
            continue                       # the test above owns that failure
        expected = set(re.findall(r"\{(\w+)\}", english))
        actual = set(re.findall(r"\{(\w+)\}", translated[key]))
        assert expected == actual, (
            f"{code}.ts '{key}' has placeholders {sorted(actual)}, "
            f"English has {sorted(expected)}"
        )


@pytest.mark.parametrize("code", _codes() + [REFERENCE])
def test_the_file_is_still_valid_syntax(code):
    """A structural smoke test, added after a bad one shipped.

    The script that inserted the translations appended an entry after a line
    that already ended in a comma, producing `"...",,` in all twelve files. The
    key/value check above passed happily — it reads pairs and never looks at the
    punctuation between them — and only the frontend build caught it. The
    frontend build is not part of this suite, so the cheap structural checks are.
    """
    text = (LOCALES / f"{code}.ts").read_text(encoding="utf-8")
    assert ",," not in text.replace(" ", ""), f"{code}.ts has a doubled comma"

    # A MISSING comma, which is the same script's other way of breaking a file.
    # It appended a new entry after the last one, which had no trailing comma
    # because nothing followed it — and every check here passed while `tsc`
    # refused all twelve files. Each entry must be separated from the next.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not _ENTRY.match(line.strip()):
            continue
        nxt = next((s for s in (l.strip() for l in lines[i + 1:]) if s), "")
        if nxt.startswith("}"):
            continue                       # last entry may omit the comma
        assert line.rstrip().endswith(","), (
            f"{code}.ts line {i + 1} is not followed by a comma: "
            f"{line.strip()[:60]}"
        )
    # en.ts closes `} as const;` because StringKey is derived from it; the
    # translations close `};` because they are typed as Partial<Strings>.
    assert re.search(r"\}\s*(?:as const)?\s*;\s*$", text), \
        f"{code}.ts does not close its object"
    assert text.count("{") == text.count("}"), f"{code}.ts braces are unbalanced"


def test_english_is_not_accidentally_left_in_a_translation():
    """A handful of strings we know were added English-only, spot-checked.

    Not a general "is this really Hindi?" test — that cannot be written — but a
    guard on the specific keys that shipped untranslated, so a future copy
    change to them cannot quietly repeat it.
    """
    watched = ["scheme.apply.cta", "documents.title", "documents.identify",
               "check.location.find"]
    english = _entries(REFERENCE)
    for code in _codes():
        translated = _entries(code)
        for key in watched:
            assert translated.get(key) != english[key], (
                f"{code}.ts '{key}' is still the English string"
            )


# --------------------------------------------------------------------------
# The defects key coverage cannot see.
#
# Everything above proves a locale holds every key. None of it can catch the
# three ways a translated interface still shows English, all of which have
# shipped at least once:
#
#   1. the template is translated and the value interpolated into it is not
#   2. the template is never asked for its values, so it prints "{facets}"
#   3. the punctuation belongs to the wrong script
#
# These are structural, so they can be tested. They are the guards that would
# have caught what the manual pass found.
# --------------------------------------------------------------------------

WEB = Path(__file__).resolve().parents[1] / "web"
VOCABULARY = WEB / "lib" / "i18n" / "vocabulary.ts"

#: Every language a string must exist in, English excluded — English is the
#: value in these tables, not a translation of it.
TRANSLATED = ("hi", "bn", "mr", "ta", "te", "gu", "kn", "ml", "pa", "or",
              "as", "ur")


def _vocabulary(table: str) -> dict[str, set[str]]:
    """One `Vocabulary` table from vocabulary.ts: entry -> languages present."""
    text = VOCABULARY.read_text(encoding="utf-8")
    start = text.index(f"export const {table}")
    block = text[start:text.index("\n};", start)]
    found: dict[str, set[str]] = {}
    for entry in re.finditer(r'\n  "?([A-Za-z][^"\n:]*?)"?: \{(.*?)\n  \},',
                             block, re.S):
        found[entry.group(1)] = set(re.findall(r"(\w+):\s*\"", entry.group(2)))
    return found


def _emitted_facets() -> set[str]:
    """The facet names `/api/discover` actually puts in a response.

    Read from the engine rather than listed here, because a list here would be
    the third copy of the same sixteen strings and the one nobody updates.
    """
    from src import discovery

    names = set(discovery._FACET_LABELS.values())
    names |= set(discovery._FLAG_FACETS.values())
    source = (Path(discovery.__file__)).read_text(encoding="utf-8")
    names |= set(re.findall(
        r'match\.(?:matched_on|unmet|unknown)\.append\("([^"]+)"\)', source))
    return names


def test_every_facet_the_engine_emits_has_a_translation():
    """Otherwise the reason a scheme matched arrives in English.

    This is the "मेल नहीं खाता gender" failure: the sentence is translated and
    the thing it is about is not. `assets` was missing when this was written —
    a scheme capping what you may own said so in English in twelve languages.
    """
    have = _vocabulary("FACET_LABELS")
    missing = sorted(_emitted_facets() - set(have))
    assert not missing, (
        f"src/discovery.py emits {missing} and FACET_LABELS has no entry for "
        f"them, so they render in English inside every translated sentence"
    )


def test_every_document_label_has_a_translation():
    """The classifier's sixteen labels, which go into a translated sentence.

    `documents.ticked` is "That looks like your {name}. Ticked off." — so an
    untranslated label reads "यह आपका Aadhaar card लगता है", at the moment
    somebody is holding the document up to a camera.
    """
    from src.documents import KNOWN_DOCUMENTS

    have = _vocabulary("DOCUMENT_LABELS")
    missing = sorted({label for label, _ in KNOWN_DOCUMENTS} - set(have))
    assert not missing, (
        f"src/documents.py classifies {missing} and DOCUMENT_LABELS has no "
        f"entry for them"
    )


@pytest.mark.parametrize("table", ["CATEGORY_LABELS", "LEVEL_LABELS",
                                   "FACET_LABELS", "DOCUMENT_LABELS"])
def test_every_vocabulary_entry_covers_every_language(table):
    """A half-translated table falls back to English for the rest.

    `label()` returns the English name when a language is absent, which is the
    right fallback and the wrong thing to discover in production.
    """
    gaps = {
        name: sorted(set(TRANSLATED) - langs)
        for name, langs in _vocabulary(table).items()
        if set(TRANSLATED) - langs
    }
    assert not gaps, f"{table} entries missing languages: {gaps}"


#: `t("key")` and friends, with whatever follows the key. A `)` there means no
#: values were passed. Dynamic keys — `t(`results.strength.${x}`)` — are not
#: matched, because there is no key here to look up.
_CALL = re.compile(r"\b(?:t|tr|tv|translate)\(\s*(?:[A-Za-z_$][\w$]*\s*,\s*)?"
                   r'"([a-zA-Z0-9_.]+)"\s*([,)])')


def _tsx_sources() -> list[Path]:
    skip = {"node_modules", ".next", "dist", "build"}
    return [p for p in WEB.rglob("*.tsx") if not skip & set(p.parts)] + [
        p for p in WEB.rglob("*.ts")
        if not skip & set(p.parts) and not p.name.endswith(".d.ts")]


def test_a_string_that_interpolates_is_never_asked_for_without_its_values():
    """`t("results.notMatchedOn")` prints the literal "{facets}".

    This shipped. The chat panel did:

        tr("results.notMatchedOn") + " " + unmet.join(", ")

    which rendered "does not meet the condition on {facets} gender, age" — a
    visible brace, English facet names, and a Latin comma — in all thirteen
    languages at once. `t()` substitutes nothing it was not given, and nothing
    warned, because every locale had the key.

    Splitting the string to wrap a React element around the placeholder is the
    one legitimate way to call it bare, and it is allowed here: `notfound.back`
    puts a link inside the sentence, and only the translation knows where in
    the sentence that link goes.
    """
    english = _entries(REFERENCE)
    offenders = []
    for path in _tsx_sources():
        text = path.read_text(encoding="utf-8")
        for call in _CALL.finditer(text):
            key, following = call.group(1), call.group(2)
            if following == ",":
                continue                   # values were passed
            if not re.search(r"\{\w+\}", english.get(key, "")):
                continue                   # nothing to substitute
            tail = text[call.end():call.end() + 24]
            if tail.lstrip(")").lstrip().startswith(".split("):
                continue                   # split around an element, on purpose
            line = text.count("\n", 0, call.start()) + 1
            offenders.append(
                f"{path.relative_to(WEB).as_posix()}:{line} {key} "
                f"-> {english[key][:48]!r}")
    assert not offenders, (
        "these calls will print a literal {placeholder}:\n  "
        + "\n  ".join(offenders))


def test_urdu_punctuates_in_its_own_script():
    """Arabic script takes `،`, not `,`.

    A Latin comma in a right-to-left line sits on the wrong side of the word
    and reads as a rendering fault. Figures are the exception and are left
    alone: `₹1,20,000` is Indian digit grouping, which is deliberately Latin
    everywhere so it matches the paper form someone is copying it onto — so
    only a comma that is not between two digits is punctuation.
    """
    punctuation = re.compile(r"(?<!\d),|,(?!\d)")
    offenders = [
        f"{key}: {value[:60]}"
        for key, value in _entries("ur").items()
        if punctuation.search(value)
    ]
    assert not offenders, (
        "ur.ts uses a Latin comma as punctuation; Arabic script takes '\u060c':"
        "\n  " + "\n  ".join(offenders))
