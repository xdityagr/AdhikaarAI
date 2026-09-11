"""Find user-visible English that is not going through t().

The first version of this script read one line at a time, and every real defect
it was written to find was invisible to it. JSX text wraps:

    <span className="text-sm text-muted-foreground">
      aimed at you, of {(card.total as number)?.toLocaleString("en-IN")} possible
    </span>

No line here holds both the `>` and the `<` around that sentence, the sentence
starts lowercase, and it has an expression in the middle of it. The script
reported 32 findings — all of them translation keys, the brand name and
generated files under .next — and passed the three pages that between them
printed "aimed at you, of 4,736 possible", "does not meet the condition on
{facets} gender, age" and "You keep Rs 12,000." in all thirteen languages.

So this one reads the whole file: it blanks the comments, collapses
`{expressions}` to a marker so a sentence broken by one is still read as one
sentence, and then looks for runs of English between tags.

    python scripts/audit_i18n.py                 # everything under web/
    python scripts/audit_i18n.py web/app/chat    # one directory or file

Exits non-zero when it finds something, so it can gate a commit. Expect false
positives on prose inside a `<code>` sample and on anything genuinely not
translated by us — scheme names, portal names. Read the list, do not trust it.
"""
from __future__ import annotations

import argparse
import pathlib
import re

SKIP_DIRS = {"node_modules", ".next", "dist", "build", ".turbo", "coverage"}

#: An expression with nothing nested inside it and no tag in it — `{count}`,
#: `{t("chat.open")}`, `{(card.total as number)?.toLocaleString("en-IN")}`.
#: Collapsed innermost-first, repeatedly, which reaches every expression that
#: holds no JSX however deeply it is nested.
#:
#: An expression that DOES hold JSX is deliberately left alone. Collapsing those
#: too is what hid "Open the camera" in document-capture.tsx: the button sits
#: inside `{working ? (<Button/>) : (<Button/>)}`, so blanking the whole
#: expression blanked the text it was there to find. Conditional and mapped JSX
#: is where most of this interface lives.
INNER_EXPR = re.compile(r"\{[^{}<>]*\}", re.S)
#: The same inside a template literal, `$` included so a URL does not survive
#: as `$ /api/agent/stream` and read like three English words.
TEMPLATE_EXPR = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}", re.S)

LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
JSX_COMMENT = re.compile(r"\{\s*/\*.*?\*/\s*\}", re.S)

TEXT_NODE = re.compile(r">([^<>]+)<", re.S)

#: Props whose value is shown or read aloud.
PROP = re.compile(
    r'\b(placeholder|title|alt|aria-label|label|lede|eyebrow|blurb|caption'
    r'|description|heading|summary)\s*=\s*"([^"\n]{4,})"')

#: Display strings in object literals.
FIELD = re.compile(
    r'\b(label|blurb|title|heading|description|caption|note|body|lede)\s*:\s*'
    r'"([^"\n]{4,})"')

#: English welded onto interpolated data — `${n} km`, `matched on ${x}`. This
#: is the shape that defeats key coverage: the sentence never reaches a locale
#: file at all, so every locale has every key and the line is still English.
CONCAT = re.compile(r"`([^`\n]*\$\{[^`\n]*)`")

WORD = re.compile(r"[A-Za-z][a-z]{2,}")
KEYISH = re.compile(r"^[a-z][a-zA-Z0-9]*(?:\.[a-zA-Z0-9]+)+$")
CSSISH = re.compile(
    r"(?:^|[\s:])(?:flex|grid|text-|bg-|border|rounded|[pmwh][xytblr]?-|gap-"
    r"|min-|max-|absolute|relative|fixed|sticky|hidden|block|inline|overflow"
    r"|font-|leading-|tracking-|shadow|ring-|space-|divide-|size-|tabular"
    r"|truncate|line-clamp|sm:|md:|lg:|xl:|hover:|focus:|group|items-|justify-"
    r"|self-|order-|col-|row-|aspect-|object-|cursor-|select-|pointer-"
    r"|transition|duration-|ease-|animate-|motion-|opacity-|z-|whitespace-)")
SKIP_TEXT = re.compile(r"^(?:https?:|/|#|@|\.|[A-Z0-9_]+$|use (?:client|server)$)")
SKIP_LINE = re.compile(r'^\s*(?:import\b|export \* |from ")')
#: A name, not a string. Translating it sends someone to ask for a thing that
#: does not exist — the same rule the scheme and portal names live under.
BRAND = re.compile(r"^(?:Yojna Setu|Adhikaar ?AI)$")

#: A JSX text run is prose. Anything holding these is code that happened to sit
#: between a `>` and a `<` — a generic parameter, mostly: `useState<Row[]>([])`.
#: Braces are in that list because every expression holding no JSX has already
#: been blanked by the time a run is tested, so a brace that survived belongs to
#: a conditional wrapper — `{turn.trace?.length ? (` — and not to prose.
CODE = re.compile(r"[;=()\[\]`&|{}]|=>"
                  r"|\b(?:const|let|return|function|await|null|Props)\b")


def words(text: str) -> list[str]:
    return WORD.findall(text)


def interesting(text: str, *, near_data: bool = False) -> bool:
    """English a reader would see.

    Two words ordinarily. One is enough beside interpolated data, because that
    is how a unit or a tail gets left behind: `{n} found`, `{km} km`, `{n} yr`.
    """
    text = text.replace("\x00", " ").strip()
    if not text or SKIP_TEXT.match(text) or KEYISH.match(text):
        return False
    if CSSISH.search(text) or BRAND.match(text):
        return False
    if "/" in text and " " not in text:
        return False                       # a path, an import, a content type
    found = words(text)
    return len(found) >= (1 if near_data and found else 2)


def line_of(src: str, index: int) -> int:
    return src.count("\n", 0, index) + 1


def blank(match: re.Match) -> str:
    """Replace a comment with spaces, so the line numbers still line up."""
    return re.sub(r"[^\n]", " ", match.group(0))


def mask(match: re.Match) -> str:
    """Replace an expression with a marker, keeping its newlines.

    The newlines matter: an expression in this codebase is routinely six lines
    long, and collapsing them away reported every finding in chat-panel.tsx
    about 270 lines above where it actually was.
    """
    return "".join("\n" if c == "\n" else "\x00" for c in match.group(0))


def collapse(src: str) -> str:
    """Blank every expression that holds no JSX, innermost first."""
    while True:
        reduced = INNER_EXPR.sub(mask, src)
        if reduced == src:
            return reduced
        src = reduced


def audit(path: pathlib.Path) -> list[tuple[int, str, str]]:
    src = path.read_text(encoding="utf-8")
    src = JSX_COMMENT.sub(blank, src)
    src = BLOCK_COMMENT.sub(blank, src)
    src = LINE_COMMENT.sub(blank, src)
    src = "\n".join("" if SKIP_LINE.match(l) else l for l in src.splitlines())

    hits: list[tuple[int, str, str]] = []

    for rx, group, kind in ((PROP, 2, "prop"), (FIELD, 2, "field")):
        for m in rx.finditer(src):
            if interesting(m.group(group)):
                hits.append((line_of(src, m.start()), kind, m.group(group)))

    for m in CONCAT.finditer(src):
        body = TEMPLATE_EXPR.sub("\x00", m.group(1))
        literal = body.replace("\x00", "").strip()
        # `field.${key}` and `profile-${id}` build a key, they do not say
        # anything. The tell is whitespace: English welded onto data always has
        # a space in the half that is English — `matched on ${x}`, `${n} km`.
        if " " not in literal or CODE.search(literal):
            continue
        if interesting(body, near_data=True):
            hits.append((line_of(src, m.start()), "concat",
                         " ".join(m.group(1).split())))

    collapsed = collapse(src)
    for m in TEXT_NODE.finditer(collapsed):
        run = m.group(1)
        if CODE.search(run.replace("\x00", "")):
            continue
        if interesting(run, near_data="\x00" in run):
            shown = " ".join(run.replace("\x00", "{}").split())
            hits.append((line_of(collapsed, m.start()), "jsx",
                         re.sub(r"(?:\{\})+", "{}", shown)))

    return sorted(set(hits))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="files or dirs; default web/")
    args = parser.parse_args()

    files: list[pathlib.Path] = []
    for root in (pathlib.Path(p) for p in (args.paths or ["web"])):
        if root.is_file():
            files.append(root)
            continue
        for pattern in ("*.tsx", "*.ts"):
            files += [p for p in root.rglob(pattern)
                      if not SKIP_DIRS & set(p.parts)
                      and "i18n" not in p.parts
                      and not p.name.endswith(".d.ts")]

    findings = {}
    for path in sorted(set(files)):
        hits = audit(path)
        if hits:
            findings[path.as_posix()] = hits

    total = sum(len(v) for v in findings.values())
    print(f"{total} suspect strings across {len(findings)} files\n")
    for path, hits in sorted(findings.items(), key=lambda kv: -len(kv[1])):
        print(f"{path}  ({len(hits)})")
        for lineno, kind, text in hits:
            print(f"  {lineno:5}  {kind:6}  {text[:96]}")
        print()
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
