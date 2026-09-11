"""
Land holding, read out of prose into a number a computer can compare.

The PS calls converting prose eligibility into machine rules "the hard and
interesting part", and land is the case that shows why. myScheme publishes
caste, gender, age and income as structured fields; land appears nowhere except
inside `eligibilityDescription_md`, as a sentence.

Only 271 schemes of 4,736 mention land or an asset test at all, and 99 of those
state a number with a unit. That is small enough to extract deterministically and
check by hand, which is the point: **no model runs here.** A model reading
eligibility and emitting a number nobody verified is the exact failure the PS
warns about — "telling someone they qualify when they do not is a real harm" —
and a regex that declines to guess is worth more than an LLM that always answers.

FOUR THINGS THE PROSE DOES THAT NAIVE MATCHING GETS WRONG

1. **Most numbers are minimums, not ceilings.** "should hold a minimum of 1.5
   acres" is a requirement to own land, and reading it as a cap inverts who
   qualifies. Direction is decided from explicit cue words, and a match with no
   cue is discarded rather than assumed.

2. **"Landless" is usually an inclusion.** "Farmers ... and Landless persons of
   Himachal Pradesh are eligible" widens the scheme; "The family of the applicant
   should be landless" restricts it. Only the second is a rule. Treating every
   mention as a requirement would wrongly exclude every landowner from schemes
   that were explicitly opening their doors.

3. **Not every hectare is the applicant's field.** "water spread area of 2
   hectares", "the hatchery should have a minimum area of 0.50 hectares", "at
   least 60 hectares of land should be available for tea plantation" are project
   dimensions. A window has to name the applicant's own possession to count.

4. **A bigha is not a fixed size.** It ranges from about a quarter of an acre to
   more than one-and-a-half depending on the state, and kanal, guntha, cent and
   decimal vary too. Converting them would invent precision. They are recorded as
   evidence with no number, so the scheme says "this depends on land" and the
   product asks the person to check rather than computing a wrong answer.

Every extracted value carries the sentence it came from, so any single decision
can be audited against the source by eye.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

#: 1 hectare in acres. The only conversion done here, because it is the only one
#: that is the same in every state.
_ACRES_PER_HECTARE = 2.47105

#: Units we will turn into a number.
_CONVERTIBLE = {
    "acre": 1.0, "acres": 1.0,
    "hectare": _ACRES_PER_HECTARE, "hectares": _ACRES_PER_HECTARE,
    "ha": _ACRES_PER_HECTARE,
}

#: Units that are real, local, and not a fixed size. Recorded, never converted.
_LOCAL_UNITS = {"bigha", "bighas", "kanal", "kanals", "guntha", "gunthas",
                "cent", "cents", "decimal", "decimals", "katha", "kathas"}

_UNIT_RE = "|".join(sorted(set(_CONVERTIBLE) | _LOCAL_UNITS, key=len, reverse=True))
_NUMBER = re.compile(
    rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_RE})\b", re.I)

#: The window has to be about land, not about a pond or a building.
_LAND_NOUN = re.compile(
    r"\b(land|landholding|land ?holding|farm|farmland|field|acreage|"
    r"agricultur\w*|cultivab\w*|cultivat\w*|irrigat\w*|holding)\b", re.I)

#: …and about the applicant HAVING it. Without this, project dimensions and
#: scheme-wide caps read as personal eligibility.
_POSSESSION = re.compile(
    r"\b(own|owns|owned|owning|hold|holds|holding|possess|possesses|"
    r"possessing|have|has|having|in the name of|belonging to)\b", re.I)

#: Windows that are describing infrastructure rather than a person's holding,
#: or a cap on what the scheme will subsidise rather than on who may apply.
#: "The maximum land area allowed under the scheme is 2 hectares" limits the
#: grant, not the applicant — a farmer with 5 acres is still eligible, for 2 of
#: them — so reading it as a ceiling would wrongly exclude exactly the people it
#: was written to pay.
_NOT_A_HOLDING = re.compile(
    r"\b(water ?spread|hatchery|pond|tank|plantation|nursery|shed|building|"
    r"godown|unit area|project area|premises|per season|in a season|"
    r"allowed under the scheme|under the scheme is|assistance (?:is )?limited|"
    r"subsid\w+ (?:is )?limited|allowed per beneficiar\w+|per beneficiar\w+|"
    r"lettable|rooms?)\b", re.I)

#: A definition of a term, not this scheme's rule. "(Note: A small farmer is one
#: who owns up to 5 acres…)" explains vocabulary used elsewhere; treating it as
#: the scheme's own ceiling attributes a rule to a scheme that never set it.
_DEFINITION = re.compile(
    r"\b(is one who|is defined as|means a|refers to|definition of|"
    r"are those who|i\.e\.|namely)\b", re.I)

_MAX_CUE = re.compile(
    r"\b(not more than|no more than|not exceed\w*|not above|upto|up to|"
    r"maximum|max\.?|at most|or less|less than|below|within|ceiling|"
    r"should not own|shall not own|not owning more than|limited to)\b", re.I)

_MIN_CUE = re.compile(
    r"\b(at least|minimum|min\.?|not less than|or more|more than|"
    r"above|exceeding|possess\w* at least)\b", re.I)

#: Only these may follow a figure and change its direction. Anything further
#: downstream is about something other than this number.
_TRAILING_MAX = re.compile(r"^\W*(or less|or below|or fewer|or under)\b", re.I)
_TRAILING_MIN = re.compile(r"^\W*(or more|or above|and above|or higher)\b", re.I)

#: "Landless" as an actual requirement, not as one more eligible category.
_LANDLESS_REQUIRED = re.compile(
    r"\b(?:applicant|family|beneficiary|household|he|she|they)\b[^.\n]{0,40}"
    r"\b(?:should|must|shall|has to|have to)\s+be\s+landless", re.I)


@dataclass
class LandRule:
    """What one scheme says about land, and where it said it."""
    min_acres: Optional[float] = None
    max_acres: Optional[float] = None
    landless_required: bool = False
    #: Mentions land in a way we could not turn into a number — a bigha figure,
    #: or prose with no cue. The product must say "this scheme has a land
    #: condition, check it" rather than silently ignoring it.
    unquantified: bool = False
    evidence: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.min_acres is not None or self.max_acres is not None
                    or self.landless_required or self.unquantified)


#: A sentence ends at a full stop FOLLOWED BY SPACE, or at a newline. Splitting
#: on any "." cuts "0.2 hectares" in half, which truncated the evidence and — far
#: worse — hid the start of a sentence from the checks that read it: a note
#: defining "small farmer" survived the definition filter because the filter only
#: ever saw the half after a decimal point.
_SENTENCE_END = re.compile(r"(?<!\d)\.(?=\s)|\n|;")


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence the match sits in, so the evidence can be read on its own."""
    left = 0
    for m in _SENTENCE_END.finditer(text, 0, start):
        left = m.end()
    right_match = _SENTENCE_END.search(text, end)
    right = right_match.start() if right_match else len(text)
    return re.sub(r"\s+", " ", text[left:right]).strip(" -*\t")


def extract(eligibility_md: Optional[str]) -> LandRule:
    """Read every land condition a scheme states. Conservative by construction.

    Anything ambiguous becomes `unquantified` rather than a number: a scheme we
    cannot read must fall back to "check this yourself", never to a comparison
    against a figure we guessed.
    """
    rule = LandRule()
    if not eligibility_md:
        return rule
    text = eligibility_md
    #: (sentence, direction, acres) — held until every match is seen, so a
    #: sentence carrying two ceilings can be recognised as conditional.
    found: list[tuple[str, str, float]] = []

    if _LANDLESS_REQUIRED.search(text):
        rule.landless_required = True
        match = _LANDLESS_REQUIRED.search(text)
        rule.evidence.append(_sentence_around(text, match.start(), match.end()))

    for match in _NUMBER.finditer(text):
        window = text[max(0, match.start() - 130):match.end() + 90]

        if not _LAND_NOUN.search(window):
            continue                       # a number about something else
        if _NOT_A_HOLDING.search(window):
            continue                       # a pond, a shed, a subsidy cap
        if not _POSSESSION.search(window):
            continue                       # not the applicant's own holding

        sentence = _sentence_around(text, match.start(), match.end())
        if _DEFINITION.search(sentence):
            continue                       # explaining a term, not setting a rule
        unit = match.group("unit").lower()
        value = float(match.group("value"))

        if unit in _LOCAL_UNITS:
            # A real condition in a unit whose size depends on the district.
            rule.unquantified = True
            rule.evidence.append(sentence)
            continue

        acres = value * _CONVERTIBLE[unit]
        # Cues are read from the text BEFORE the number — "not more than 10
        # acres". After it, only the handful of phrases that trail a figure are
        # allowed: a wide window downstream read "…more than 5 acres with
        # accommodation of not more than 9 lettable rooms" and turned a minimum
        # into a maximum, because the cue it found belonged to the rooms.
        before = text[max(0, match.start() - 80):match.start()]
        after = text[match.end():match.end() + 18]
        is_max = bool(_MAX_CUE.search(before) or _TRAILING_MAX.search(after))
        is_min = bool(_MIN_CUE.search(before) or _TRAILING_MIN.search(after))

        if is_max and not is_min:
            found.append((sentence, "max", acres))
        elif is_min and not is_max:
            found.append((sentence, "min", acres))
        else:
            # No cue, or both — "a minimum of 0.25 hectare and maximum 2" needs
            # a reader, not a regex. Flagged, not guessed.
            rule.unquantified = True
            rule.evidence.append(sentence)

    # Two different ceilings anywhere in one scheme means a CONDITIONAL rule, and
    # there is no way to choose between them without knowing which land the
    # person has. Punjab's old-age pension is the case that proves it:
    #
    #     Beneficiary should own any of the below mentioned amount of land :-
    #        Maximum 2.5 Acre Nehri or Chahi Land, OR
    #        Maximum 5 Acre Barani Land, OR
    #        Waterlogged 5 Acre Land.
    #
    # Taking the smallest gives 2.5 acres and denies the pension to a man with
    # four acres of Barani land who is plainly entitled to it. The alternatives
    # sit on separate lines, so checking within a sentence was not enough — this
    # has to be per scheme.
    for direction in ("max", "min"):
        values = {round(acres, 3) for _, kind, acres in found if kind == direction}
        if len(values) > 1:
            rule.unquantified = True
            rule.evidence.extend(s for s, kind, _ in found if kind == direction)
            found = [f for f in found if f[1] != direction]

    for sentence, kind, acres in found:
        if kind == "max":
            rule.max_acres = acres if rule.max_acres is None else min(rule.max_acres, acres)
        else:
            rule.min_acres = acres if rule.min_acres is None else max(rule.min_acres, acres)
        rule.evidence.append(sentence)

    # Deduplicate while keeping order; the same sentence often carries two units.
    rule.evidence = list(dict.fromkeys(rule.evidence))[:4]
    return rule
