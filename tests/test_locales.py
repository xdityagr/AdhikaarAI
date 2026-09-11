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
