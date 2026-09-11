"""
Filling the form — the step this product used to skip.

Until now it took someone as far as "here is the scheme, here is roughly how
to apply, here is the office", and the tracker picked up after they had
applied. The hardest part was the gap in the middle, and it is the part that
actually decides whether a person gets the money.

WHAT THIS DOES NOT DO, AND WILL NOT

It does not submit anything. The corpus deep-links to hundreds of different
state and central portals; they authenticate with OTPs, they use CAPTCHAs, and
none of them publish an API. Driving them would mean holding someone's Aadhaar
number and bank credentials — the precise arrangement this product tells people
to refuse, because it is what every agent who charges a poor household a fee
also offers.

And it would fail quietly. A submission that silently did not go through leaves
someone believing they have applied, so they stop chasing it, stop asking at
the office, and miss the window. That is a worse outcome than never starting.

WHAT IT DOES

Produces a completed application pack: every field the scheme asks for, filled
from what the person has already told us; the documents to carry, checked
against what they say they have; the steps in order; and the office that can
actually process it. Printable, or readable aloud, in their own language.

WHERE THE MODEL IS ALLOWED

The same wall as everywhere else in this codebase. The model may phrase a field
label, explain what a document is, and map a messy answer onto a field. It may
NOT decide eligibility, invent a document the scheme did not list, or produce a
rupee figure. Every item below comes from the corpus or from the person.

Nothing is stored. The profile arrives with the request and leaves with the
response — the same promise the wizard makes.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.catalog import get_scheme
from src.discovery import CORPUS_PATH


# ---------------------------------------------------------------------------
# What an application asks for
# ---------------------------------------------------------------------------

@dataclass
class Field:
    """One line of the form."""
    key: str
    label: str
    value: str = ""
    """Where the value came from, so nothing on the sheet is unattributable."""
    source: str = ""
    required: bool = True
    """Set when we could not fill it and the person must write it themselves."""
    blank: bool = False


@dataclass
class Document:
    text: str
    """True when the person said they hold it, False when they said they do
    not, None when nobody has asked yet — the three states matter, because
    "not asked" must never be shown as "missing"."""
    held: Optional[bool] = None


@dataclass
class Note:
    """A sentence we wrote, not the government. `code` is what the interface
    translates on; `text` is English and is what anything without a translation
    layer prints."""
    code: str
    text: str


@dataclass
class Pack:
    slug: str
    name: str
    official_url: str = ""
    mode: str = ""
    fields: list[Field] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    """False when the scheme itself has no published process — we say so
    rather than inventing one."""
    has_process: bool = True


# The fields nearly every Indian scheme application opens with. Kept here and
# not asked of the model, because a form that asks for a different set each
# time it is generated is not a form.
#
# Aadhaar is deliberately ABSENT. Almost every scheme wants it and we still do
# not take it: an Aadhaar number typed into a website is the thing this
# audience is most often defrauded with, and the person can write it on the
# printed sheet themselves, once, in their own hand.
CORE_FIELDS: list[tuple[str, str]] = [
    ("full_name", "Full name (as on your documents)"),
    ("parent_name", "Father's / husband's name"),
    ("dob", "Date of birth"),
    ("gender", "Gender"),
    ("category", "Category (SC / ST / OBC / General)"),
    ("address", "Address"),
    ("state", "State"),
    ("district", "District"),
    ("pincode", "PIN code"),
    ("mobile", "Mobile number"),
    ("income", "Annual family income"),
]

# Added only when the scheme is a credit product — asking a widow applying for
# a pension about her project cost is how a form loses someone on page one.
CREDIT_FIELDS: list[tuple[str, str]] = [
    ("purpose", "What the money is for"),
    ("project_cost", "Total cost of the work"),
    ("own_contribution", "How much you can put in yourself"),
    ("bank_name", "Bank name and branch"),
]

STUDENT_FIELDS: list[tuple[str, str]] = [
    ("institution", "School or college name"),
    ("course", "Course or class"),
    ("year", "Year of study"),
]

CREDIT_WORDS = ("loan", "credit", "finance", "margin money", "subsidy",
                "term loan", "working capital", "entrepreneur")
STUDENT_WORDS = ("scholarship", "student", "education", "fellowship", "tuition",
                 "school", "college", "merit")


def _looks_like(text: str, words: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in words)


# ---------------------------------------------------------------------------
# Reading the scheme's own words
# ---------------------------------------------------------------------------

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")

#: myScheme's machine translation puts spaces inside the bold markers, so the
#: `**Step 1:**` that comes back from Hindi is `* * चरण 1: * *`. The markers are
#: still there; they have just stopped parsing as bold, and they reached the
#: page as literal asterisks in the middle of the instructions.
#: Spaces WITHIN a line, never a newline: `\s` here would match the blank line
#: between `**Offline**` and the first step and weld the heading's closing
#: marker to the step's opening one, which is how the heading survived the
#: filter below as the literal item "Offline*".
_MANGLED_BOLD = re.compile(r"\*[ \t]+\*")

#: A step label, in any language the corpus carries: one or two words and a
#: small number, then a colon. "Step 4:", "चरण 2:", "படி 3:".
#:
#: Two things depend on finding these. The translated text often arrives with
#: every step on ONE line — Hindi has three newlines where English has seven —
#: so the label is the only boundary between one instruction and the next. And
#: the label itself is redundant once found, because the renderer numbers the
#: list: printing it gives "1. Step 1: ..." and, where the source repeats a
#: number (this corpus has schemes with two "Step 1"s), a list that contradicts
#: its own numbering.
#:
#: The number is written in Latin digits in every language here, which is what
#: makes one pattern enough. `[^\W\d_]` is "a letter in any script".
_STEP_LABEL = re.compile(
    r"\*{0,2}\s*"
    r"[^\W\d_]{2,15}(?:\s+[^\W\d_]{2,15})?"
    r"\s*\d{1,2}\s*[:.]"
    r"\s*\*{0,2}\s*",
    re.UNICODE,
)

#: A line that is nothing but a short bold run — `**Offline**`. It is the
#: application MODE, not a step, and `detect_mode` already reads it from the
#: raw markdown, so numbering it as step 1 both miscounts the steps and leaves
#: the word untranslated on a translated page.
_MODE_HEADING = re.compile(r"^\*\*\s*([^*]{1,30}?)\s*\*\*$")


def _split_on_labels(line: str) -> list[str]:
    """One line into one chunk per step label found inside it."""
    cuts = [m.start() for m in _STEP_LABEL.finditer(line) if m.start() > 0]
    if not cuts:
        return [line]
    chunks, previous = [], 0
    for cut in cuts:
        chunks.append(line[previous:cut])
        previous = cut
    chunks.append(line[previous:])
    return chunks


def parse_list(markdown: Optional[str], limit: int = 24) -> list[str]:
    """Pull the list items out of a markdown block.

    myScheme writes these as ordered lists whose numbers are all "1." — the
    renderer counts, the text does not — so the marker is stripped rather than
    trusted, and prose paragraphs are kept as their own items so a scheme that
    wrote its documents as a sentence is not silently reduced to nothing.

    The same principle now covers the "Step 1:" labels written into the prose,
    for the same reason and one more: in the translated text they are often the
    only thing separating one instruction from the next.
    """
    if not markdown or not markdown.strip():
        return []

    markdown = _MANGLED_BOLD.sub("**", markdown)

    # A single mode heading at the top is this document's mode and belongs to
    # `detect_mode`. TWO of them — an Online section and an Offline one — are
    # separators between two different procedures, and dropping those would
    # silently merge two sets of instructions into one list.
    lines = [raw.strip() for raw in markdown.splitlines()]
    headings = [i for i, line in enumerate(lines) if _MODE_HEADING.match(line)]
    drop = set(headings[:1]) if len(headings) == 1 else set()

    items: list[str] = []
    for index, line in enumerate(lines):
        if not line or index in drop:
            continue
        for chunk in _split_on_labels(line):
            text = chunk.strip()
            if not text:
                continue
            matched = _BULLET.match(text)
            text = matched.group(1) if matched else text
            # The label, once it has done its job of marking the boundary.
            label = _STEP_LABEL.match(text)
            if label and label.end() < len(text):
                text = text[label.end():]
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)          # bold
            # Links. The space in `]\s*(` is not cosmetic: the translated
            # records carry `[संबंधित प्राधिकारी] (https://…)` with a space
            # between the two halves, which is not a link any more — so the
            # brackets survived onto the page around the only words in the
            # sentence a person might click.
            text = re.sub(r"\[([^\]]+)\]\s*\(([^)]+)\)", r"\1 (\2)", text)
            text = re.sub(r"^#{1,6}\s*", "", text).strip()
            # myScheme's prose is converted from rich text and carries HTML through
            # with it. Two things reached the screen because of that: a bare <br>
            # rendered as its own numbered step, and "click on &#39;New&#39; button"
            # shown verbatim to someone being told how to apply. Tags go first so a
            # stripped <br> leaves an empty line that the length check drops;
            # entities are unescaped after, so a literal &amp;#39; in the source
            # cannot be decoded twice into a quote that was never there.
            text = re.sub(r"<[^>]{1,40}>", " ", text)
            text = html.unescape(text)
            text = re.sub(r"\s{2,}", " ", text).strip()
            # Markers left over at either end, stripped LAST.
            #
            # `**bold**` is removed as a pair and `* item` as a bullet, but
            # neither catches an unpaired run — and `_MANGLED_BOLD` turns the
            # translated `* * * *` into `****`, which is not a pair either. A
            # blockquote `>` survives both passes untouched.
            #
            # Last, because `html.unescape` above turns `&gt;` into `>`: doing
            # this before it left 2,058 English steps still beginning with a
            # blockquote marker that did not exist yet when the strip ran.
            #
            # They reach the page as punctuation in the middle of instructions
            # somebody is trying to follow: "**** The interested applicant
            # should visit…".
            text = re.sub(r"^[*_>\s]+", "", text)
            text = re.sub(r"[*_\s]+$", "", text)
            if len(text) > 2:
                items.append(text)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break               # the inner break only leaves this line
    return items


def detect_mode(application_md: Optional[str]) -> str:
    """Online, offline, or both — it changes the entire instruction.

    myScheme states the mode in a heading of its own — `**Offline**` — and when
    it does, that heading is the answer and the keyword sweep below is not
    consulted. The sweep counts a URL anywhere in the text as evidence of an
    online route, so an offline procedure that merely LINKS to the form to
    print reads as "both", and the person is told they can apply online when
    the same document says they must go to the office.

    The heading stays in English in the translated records, which is why
    matching it in English is enough.
    """
    raw = application_md or ""
    headings = [m.group(1).strip().lower()
                for m in (_MODE_HEADING.match(line.strip())
                          for line in raw.splitlines())
                if m]
    stated = {h for h in headings if h in ("online", "offline")}
    if stated:
        return "both" if len(stated) > 1 else stated.pop()

    text = raw.lower()
    online = "online" in text or "portal" in text or "http" in text
    offline = "offline" in text or "in person" in text or "branch" in text \
        or "office" in text or "csc" in text
    if online and offline:
        return "both"
    if online:
        return "online"
    if offline:
        return "offline"
    return ""


# ---------------------------------------------------------------------------
# Building the pack
# ---------------------------------------------------------------------------

# What the wizard already collects, mapped onto form fields, so nobody is
# asked twice for something they typed on the way in.
PROFILE_KEYS = {
    "full_name": ("full_name", "name"),
    "parent_name": ("parent_name", "father_name", "guardian"),
    "dob": ("dob", "date_of_birth"),
    "gender": ("gender",),
    "category": ("category", "caste"),
    "address": ("address",),
    "state": ("state",),
    "district": ("district",),
    "pincode": ("pincode", "pin"),
    "mobile": ("mobile", "phone"),
    "income": ("income", "annual_income", "family_income"),
    "purpose": ("purpose", "need"),
    "project_cost": ("project_cost", "cost"),
    "own_contribution": ("own_contribution", "contribution"),
    "bank_name": ("bank_name", "bank"),
    "institution": ("institution", "school", "college"),
    "course": ("course",),
    "year": ("year",),
}


def _from_profile(key: str, profile: dict) -> str:
    for candidate in PROFILE_KEYS.get(key, (key,)):
        value = profile.get(candidate)
        if value not in (None, "", []):
            return str(value)
    return ""


def build(
    slug: str,
    profile: Optional[dict] = None,
    lang: str = "en",
    corpus_path: Path = CORPUS_PATH,
    held: Optional[dict] = None,
) -> Optional[Pack]:
    """The completed pack for one scheme and one person.

    `profile` is whatever the person has already told the wizard or the
    assistant. Everything it does not cover is left blank ON THE SHEET rather
    than guessed — a form filled with a plausible invention is worse than a
    form with a gap, because the gap gets noticed at the counter and the
    invention does not.
    """
    scheme = get_scheme(slug, lang=lang, corpus_path=corpus_path)
    if scheme is None:
        return None

    profile = profile or {}
    haystack = " ".join(str(scheme.get(key) or "") for key in
                        ("name", "brief", "benefits_md", "categories"))

    wanted = list(CORE_FIELDS)
    if _looks_like(haystack, CREDIT_WORDS):
        wanted += CREDIT_FIELDS
    if _looks_like(haystack, STUDENT_WORDS):
        wanted += STUDENT_FIELDS

    fields: list[Field] = []
    for key, label in wanted:
        value = _from_profile(key, profile)
        fields.append(Field(
            key=key,
            label=label,
            value=value,
            source="answered" if value else "",
            blank=not value,
        ))

    # `held` arrives from the caller — the browser owns it, because nothing about
    # a person is stored here. Three states, and the third is why this is not a
    # bool: True is "I have it", False is "I do not", and None is "nobody has
    # asked", which must never print as missing. Someone who has not been through
    # the checklist has not told us they are short of anything.
    holdings = held or {}
    documents = [Document(text=item, held=holdings.get(item))
                 for item in parse_list(scheme.get("documents_md"))]
    steps = parse_list(scheme.get("application_md"), limit=15)

    pack = Pack(
        slug=slug,
        name=(scheme.get("name") or "").strip(),
        official_url=scheme.get("official_url") or scheme.get("source_url") or "",
        mode=detect_mode(scheme.get("application_md")),
        fields=fields,
        documents=documents,
        steps=steps,
        has_process=bool(steps),
    )

    # Said plainly, every time, on the sheet itself — not buried in a footer.
    #
    # Each note carries a stable code as well as its English sentence. The web
    # interface translates on the code and so speaks all thirteen languages;
    # WhatsApp and the printed sheet have no translation layer and fall back to
    # the sentence. Sending only prose meant a Hindi page ended in an English
    # paragraph about not paying anybody a fee — the one line on the sheet that
    # most needs to be understood.
    pack.notes.append(Note(
        "no_fee",
        "No fee is required to apply for a government scheme. Nobody should "
        "ask you for money to fill this in.",
    ))
    if not documents:
        pack.notes.append(Note(
            "no_documents",
            "This scheme has not published its document list. Carry proof of "
            "identity, address, category and income, and ask at the office "
            "what else is needed.",
        ))
    if not steps:
        pack.notes.append(Note(
            "no_steps",
            "This scheme has not published its steps. The official page is "
            "linked above and is the same source we use.",
        ))
    return pack


def to_dict(pack: Pack) -> dict:
    return {
        "slug": pack.slug,
        "name": pack.name,
        "official_url": pack.official_url,
        "mode": pack.mode,
        "has_process": pack.has_process,
        "fields": [
            {"key": f.key, "label": f.label, "value": f.value,
             "required": f.required, "blank": f.blank, "source": f.source}
            for f in pack.fields
        ],
        "documents": [{"text": d.text, "held": d.held} for d in pack.documents],
        "steps": pack.steps,
        "notes": [{"code": n.code, "text": n.text} for n in pack.notes],
        "filled": sum(1 for f in pack.fields if not f.blank),
        "total": len(pack.fields),
    }
