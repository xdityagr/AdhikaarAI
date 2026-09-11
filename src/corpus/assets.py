"""
Owning things, read out of prose into a rule a computer can check.

`land.py` did the same job for land and its docstring mentions assets, which
made this look finished. It was not. Land is one asset among several, and the
others are stated in the same place and the same way: as a sentence inside
`eligibilityDescription_md`, nowhere in myScheme's structured fields.

The big one is housing. A great many schemes exist to give somebody a house, and
almost all of them say so by excluding people who already have one — so "should
not own a pucca house" is the single most common asset rule in the corpus and
also the one it is most expensive to get wrong. Telling a family in a kutcha hut
that they do not qualify for a housing scheme, because we read "house" where the
scheme wrote "pucca house", is the exact harm this project exists to prevent.

The same rules as land.py, for the same reasons. **No model runs here.** Every
value carries the sentence it came from, and anything ambiguous is flagged for a
person rather than guessed at.

FOUR THINGS THE PROSE DOES THAT NAIVE MATCHING GETS WRONG

1. **Direction is not implied by the asset.** "The applicant should possess a
   pucca house/commercial place to keep the aquarium" is a REQUIREMENT to own
   one, in a scheme about fish tanks. Reading every mention as an exclusion
   would deny an aquarium subsidy to precisely the people who qualify for it.

2. **"Pucca house" and "house" are different rules.** "Should not have a pucca
   house" leaves a kutcha house holder eligible; "should not own any house or
   house site" does not. They are recorded as different assets, and a scheme
   that says `pucca` is never widened to `house`.

3. **Not every "should not have" is about owning.** "Should not have availed
   benefit under any other Government scheme" is a prior-benefit rule; "must not
   have any major traffic violations" is a conduct rule. Neither is an asset,
   and both sit in sentences that look identical to a regex reading for
   negation.

4. **Counts are not booleans.** "Should not own more than one residential
   house" permits one. Treating it as "must own no house" excludes a family the
   scheme was written to include, so a count is flagged rather than flattened.

WHAT A PERSON IS ACTUALLY ASKED

The asset vocabulary is closed and small on purpose — six kinds, each a question
a person can answer about themselves without a document in front of them. An
asset we cannot phrase as such a question is not worth extracting, because
nothing downstream could ever ask about it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

#: The closed vocabulary. Each key is one yes/no question a person can answer.
#:
#: `pucca_house` is a strict subset of `house` and is kept separate for the
#: reason in the docstring: the two rules exclude different families, and the
#: schemes that mean one say so explicitly.
ASSETS = ("pucca_house", "house", "vehicle", "boat", "govt_job", "income_tax")

_ASSET_PATTERNS: dict[str, re.Pattern] = {
    # Ordered by specificity at match time, not here — see `_asset_in`.
    # "Pucca" on its own is an adjective, not a house. Kamdhenu's dairy subsidy
    # asks for "a pucca cattle shed with cement flooring", which was read as
    # owning a pucca house and would have excluded a dairy farmer from every
    # housing scheme she is entitled to. It has to be attached to a dwelling.
    "pucca_house": re.compile(
        r"\b(?:pucca|pakka)\s+(?:\w+\s+){0,2}?"
        r"(?:house|houses|ghar|dwelling|makan|home)\b"
        r"|\ball[- ]weather dwelling\b", re.I),
    # No bare "residence" or "resident". In this corpus those overwhelmingly
    # mean domicile, not a dwelling somebody owns — "Residence Certificate",
    # "15 years of Residence in Goa", and, in a goat-rearing subsidy, "food,
    # water, fodder, residence and concentrates expenses". Every one of those
    # read as owning a house. "Residential unit" is kept because the qualifier
    # is what makes it a building.
    # The lookbehind is for "in-house expertise", which an AICTE conference
    # grant asks its applicant institution to possess.
    "house": re.compile(
        r"\b(?<!in-)(house|houses|housing unit|dwelling|residential unit|"
        r"house ?site|homestead)\b", re.I),
    "vehicle": re.compile(
        r"\b(four[- ]?wheeler|three[- ]?wheeler|two[- ]?wheeler|motor ?vehicle|"
        r"motoris\w+ vehicle|motoriz\w+ vehicle|tractor|car|auto ?rickshaw)\b",
        re.I),
    "boat": re.compile(
        r"\b(mechanis\w+ boat|mechaniz\w+ boat|motoris\w+ boat|motoriz\w+ boat|"
        r"motoris\w+ craft|motoriz\w+ craft|fishing (?:boat|vessel|craft))\b",
        re.I),
    "govt_job": re.compile(
        r"\b(government (?:servant|employee|job|service|employment)|"
        r"govt\.? (?:servant|employee|job|service)|"
        r"(?:permanent|regular) government)\b", re.I),
    "income_tax": re.compile(
        r"\b(income[- ]?tax ?payer|income[- ]?tax assessee|"
        r"pays? income[- ]?tax|paying income[- ]?tax|"
        r"professional tax ?payer)\b", re.I),
}

#: Owning, in the sense of it being yours. Deliberately excludes "availed",
#: "received" and "benefited", which are about a past transaction rather than a
#: present possession — see point 3 in the docstring.
_POSSESS = re.compile(
    r"\b(own|owns|owned|owning|possess|possesses|possessed|possessing|"
    r"have|has|having|hold|holds|holding|in (?:his|her|their|the) name)\b",
    re.I)

#: The negation must attach to the possession, so the window between them is
#: kept short. "should not ... own" spans a clause; "should not have availed a
#: benefit and owns a house" must not read as "does not own a house".
_NEGATION = re.compile(
    r"\b(should not|shall not|must not|does not|do not|"
    r"neither|nor|without|no\b|non[- ]?owner|free from)\b", re.I)

#: Phrases that look like an ownership rule and are not one.
#: `licen` is here for the Amma Two Wheeler Scheme, which asks the applicant to
#: "possess a valid Two Wheeler / Learner License Registration" — a licence to
#: drive, in a scheme that exists to GIVE her the two-wheeler. Reading it as
#: owning one inverts who the scheme is for. "Registered" is deliberately NOT
#: excluded: a registered fishing boat is a boat somebody owns.
_NOT_OWNERSHIP = re.compile(
    r"\b(avail\w*|benefit\w*|receiv\w*|sanction\w*|allot\w*|"
    r"licen[cs]\w*|permit\b|driving|"
    r"traffic violation\w*|criminal offence\w*|conviction\w*|"
    r"applied (?:for|under)|applic\w+ under (?:any|other)|"
    r"under any other (?:government )?scheme)\b", re.I)

#: A definition or an aside, not this scheme's own rule. Same hazard as land.
_DEFINITION = re.compile(
    r"\b(is one who|is defined as|means a|refers to|definition of|"
    r"are those who|i\.e\.|namely|for the purpose of this)\b", re.I)

#: "not more than one residential house" — a permitted count, not a ban.
_COUNT = re.compile(
    r"\b(more than|at least|minimum of|maximum of|upto|up to)\s+"
    r"(?:\d+|one|two|three|a single)\b", re.I)

#: Whose asset it is. Recorded, because "in his or any family member's name" is
#: a materially wider bar than the applicant alone, and a person answering for
#: themselves would answer the narrow question and be told the wrong thing.
_FAMILY_SCOPE = re.compile(
    r"\b(family|household|spouse|wife|husband|any member|no member|"
    r"family member|dependent)\b", re.I)

#: Between the possession verb and the asset. If one of these sits in the gap,
#: the thing being owned is not the asset — it is land, or a document, or the
#: asset is merely what the land is FOR.
_OWNS_SOMETHING_ELSE = re.compile(
    r"\b(land|plot|site|certificate|document|proof|passbook|account|"
    r"for (?:the )?construction|to construct|for building|for constructing|"
    # Wanting one is not having one. A cooperative loan asks the borrower to
    # "have the intention to use the loan specifically for purchasing a fishing
    # boat" — the whole point is that they do not own a boat yet.
    r"intention|intend\w*|purchas\w*|propos\w*|to buy|acquir\w*|"
    # Possessing "sea fishing experience in any mechanized boat" is not
    # possessing a boat.
    r"experience|knowledge|skill\w*|training|qualificat\w*|membership)\b",
    re.I)

#: "have"/"has" before a participle is an auxiliary verb, not possession. The
#: Good Samaritan Scheme asks that the applicant "should have saved the life of
#: a victim of a fatal accident involving a motor vehicle", which was read as
#: owning the vehicle. Ownership participles are excepted, so "has owned" still
#: counts.
_AUXILIARY = re.compile(r"^\s+(?:been\s+)?(?!own|possess)\w+(?:ed|en)\b", re.I)

#: A house you may own OR rent is not a house you must own.
_RENT_ALTERNATIVE = re.compile(
    r"\bor\s+(?:on\s+)?rent\w*\b|/\s*rented\b|\brented house\b", re.I)

#: "If the beneficiary has his own house, there should be a toilet in it" sets a
#: condition ON the house, not a condition that you have one.
_CONDITIONAL = re.compile(r"^\s*(?:\d+[.)]\s*)?if\b|,\s*if\b", re.I)

#: A rule written as a disqualification rather than as a requirement.
_INELIGIBLE = re.compile(
    r"\b(not (?:be )?eligible|ineligible|not entitled|disqualif\w+|"
    r"shall not (?:be )?(?:eligible|considered))\b", re.I)

#: Sentence boundaries, with the same decimal guard land.py needed.
_SENTENCE_END = re.compile(r"(?<!\d)\.(?=\s)|\n|;")


@dataclass
class AssetRule:
    """What one scheme says about owning things, and where it said it."""

    #: Assets the applicant must NOT own to qualify.
    must_not_own: set[str] = field(default_factory=set)
    #: Assets the applicant MUST own. Rarer, and real — a scheme paying for an
    #: aquarium wants somewhere to put it.
    must_own: set[str] = field(default_factory=set)
    #: The rule also binds the applicant's family, not only the applicant.
    family_scope: bool = False
    #: An asset condition we could not read into a yes/no — a permitted count,
    #: a conditional, a direction with no cue. The product must say "this scheme
    #: has an asset condition, check it" rather than ignoring it.
    unquantified: bool = False
    evidence: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.must_not_own or self.must_own
                    or self.unquantified)


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Where the sentence holding this match begins and ends.

    Everything is read inside these bounds rather than inside a window of N
    characters. A fixed window bleeds across the full stop, and eligibility
    prose is a numbered list of unrelated conditions — with a 90-character
    reach, "should not be having their own house. The family should be residing
    in a tent house" took the verb from the first line and the noun from the
    second, and recorded a family living in a tent as owning a house.
    """
    left = 0
    for m in _SENTENCE_END.finditer(text, 0, start):
        left = m.end()
    right_match = _SENTENCE_END.search(text, end)
    right = right_match.start() if right_match else len(text)
    return left, right


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence the match sits in, so evidence reads on its own."""
    left, right = _sentence_bounds(text, start, end)
    return re.sub(r"\s+", " ", text[left:right]).strip(" -*\t>")


#: Most specific first. Every pucca house is a house, and the specific rule is
#: the one the scheme actually wrote.
_BY_SPECIFICITY = ("pucca_house", "boat", "vehicle", "govt_job", "income_tax",
                   "house")

#: The sentence has to be about the person applying. Without this, "the grant
#: may be used to build a house" and "the office holds the records" both read as
#: somebody's asset.
_APPLICANT = re.compile(
    # "application" is here because Biju Pucca Ghar Yojana's own text says "The
    # application should not own any pucca house". It is a typo in the source,
    # and refusing to read it loses a real housing exclusion.
    r"\b(applicant|application|beneficiar\w+|family|household|candidate|person|"
    r"he|she|they|his|her|their|worker|member)\b", re.I)


def _asset_matches(text: str):
    """Every asset mention, as (kind, start, end), specific kinds winning.

    A pucca house matches both `pucca_house` and `house`, and yielding both
    would record two rules from one clause — one of them wrong, since "should
    not own a pucca house" says nothing about a kutcha one. Spans already
    claimed by a more specific kind are therefore skipped.
    """
    claimed: list[tuple[int, int]] = []
    for kind in _BY_SPECIFICITY:
        for match in _ASSET_PATTERNS[kind].finditer(text):
            # Within a few words of an already-claimed, more specific mention.
            if any(abs(match.start() - s) < 25 for s, _ in claimed):
                continue
            claimed.append((match.start(), match.end()))
            yield kind, match.start(), match.end()


def extract(eligibility_md: Optional[str]) -> AssetRule:
    """Read every asset condition a scheme states. Conservative by construction.

    A sentence we cannot read becomes `unquantified` rather than a guess: a
    scheme whose asset rule we misread either denies somebody what they are
    owed, or tells them to travel to an office that will turn them away.
    """
    rule = AssetRule()
    if not eligibility_md:
        return rule

    text = eligibility_md
    # Iterate over the ASSET, which is rare and specific, and then look for the
    # possession around it — never the other way round. Scanning for "have",
    # "has" and "holding" first matches almost every sentence in the corpus and
    # then asks a 140-character window to decide what it was about; that read
    # "Police personnel in the ranks of ... Sub-Inspector" as owning a house.
    for match in _asset_matches(text):
        kind, start, end = match
        left, right = _sentence_bounds(text, start, end)
        sentence = re.sub(r"\s+", " ", text[left:right]).strip(" -*\t>")
        if not sentence or _DEFINITION.search(sentence):
            continue

        # The rule has to be about the applicant, not about the scheme, the
        # office, or what the grant may be spent on.
        if not _APPLICANT.search(sentence):
            continue

        # The possession verb must come BEFORE the asset and inside the same
        # sentence, because the asset has to be its object. "The house of the
        # applicant has a functional toilet" owns a toilet, not a house, and
        # reads identically to a regex that will take a verb from either side.
        possession = None
        for candidate in _POSSESS.finditer(text, left, start):
            possession = candidate           # the closest one before the asset
        if possession is None:
            continue                      # mentioned, not owned

        # FLAGGING COMES BEFORE SKIPPING, deliberately.
        #
        # Both of these reach a skip further down by coincidence — a count sits
        # next to the word "land", and a disqualification happens to contain
        # the word "benefits" — and a silent skip is the worse failure of the
        # two. A flagged scheme tells the person to check; a skipped one tells
        # them nothing and lets them travel to an office to be turned away.
        if _COUNT.search(text[max(left, start - 30):start]):
            # "or more than one residential house" permits one. A yes/no cannot
            # say that, so it goes to a person.
            rule.unquantified = True
            rule.evidence.append(sentence)
            continue
        if _INELIGIBLE.search(sentence):
            # "The student whose parent owns a house ... is not eligible" is a
            # must-NOT-own written the long way round, with the negation
            # attached to the eligibility rather than to the verb. Inverting it
            # automatically would be guessing.
            rule.unquantified = True
            rule.evidence.append(sentence)
            continue

        window = text[left:right]
        if _NOT_OWNERSHIP.search(window):
            continue                      # availed a benefit, not owns a thing
        if _AUXILIARY.match(text[possession.end():possession.end() + 30]):
            continue                      # "have saved", not "have a house"

        if _CONDITIONAL.search(sentence) or _RENT_ALTERNATIVE.search(sentence):
            rule.unquantified = True
            rule.evidence.append(sentence)
            continue

        # What sits between the verb and the asset decides what is owned.
        # "must own land for house construction" owns LAND — that is land.py's
        # rule, and recording it here would invent a housing condition out of a
        # land one and exclude the landless family it was written for.
        between = text[possession.end():start]
        if _OWNS_SOMETHING_ELSE.search(between):
            continue

        # "The student whose parent/guardian owns a house ... is not eligible"
        # is a must-NOT-own written the long way round, and the negation is
        # attached to the eligibility rather than to the verb. Inverting it
        # automatically would be guessing; it goes to a person.
        if _INELIGIBLE.search(sentence):
            rule.unquantified = True
            rule.evidence.append(sentence)
            continue

        # Negation is read from before the possession verb only. After it, the
        # "not" belongs to whatever comes next — the aquarium scheme says
        # "should not have benefited ... should possess a pucca house", and a
        # window reaching backwards past the full stop inverts the second rule.
        # `possession` carries an absolute offset, so the negation is read from
        # the start of the sentence up to the verb — not from an offset added
        # to a window start, which double-counted and lost the "not" in
        # "should not own any house", turning an exclusion into a requirement.
        negated = bool(_NEGATION.search(text[left:possession.start()]))

        if negated:
            rule.must_not_own.add(kind)
        else:
            rule.must_own.add(kind)
        if _FAMILY_SCOPE.search(window):
            rule.family_scope = True
        rule.evidence.append(sentence)

    # A scheme that appears to both require and forbid the same asset is a
    # scheme we have misread, or one whose prose is genuinely conditional.
    # Either way the answer is a person, not a verdict.
    contradictory = rule.must_not_own & rule.must_own
    if contradictory:
        rule.unquantified = True
        rule.must_not_own -= contradictory
        rule.must_own -= contradictory

    # A pucca-house rule already implies a house; recording both turns one
    # stated rule into two, and the general one is the one we did not read.
    # CLSS writes "should not own a pucca house (an all-weather dwelling unit)"
    # — the parenthetical is the same rule restated, not a second, wider one.
    for side in (rule.must_not_own, rule.must_own):
        if "pucca_house" in side:
            side.discard("house")

    rule.evidence = list(dict.fromkeys(rule.evidence))[:4]
    return rule
