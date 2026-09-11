"""
Inbound voice — the engine as tools, not as a caller.

THE ONE DECISION THIS MODULE IS BUILT AROUND

Our agent cannot be on a phone call. `src/agent.py:904` measures a turn at
twenty to sixty seconds — four model round-trips and up to seven lookups — and
`stream()` emits its text as one block, so time-to-first-word equals
time-to-full-answer. Sixty seconds of silence on a phone call is a dropped call.

So the conversation is driven by the telephony provider's own fast model, and
this module is what that model calls. That inverts the latency problem into one
already solved: the lookups are fast, it is the agent loop around them that is
slow.

    discover_with_credit(...)   103-115 ms     (measured, warm, limit=40)
    find_schemes tool            110 ms        (the whole tool, end to end)

NO MODEL RUNS ON THIS PATH. Not for matching, not for eligibility, not for
phrasing. Every number a caller hears is computed by `src/discovery.py` and
carried through unchanged. A model may choose the words around the answer; it
may not decide whether someone qualifies. Telling a person they qualify when
they do not is a real harm, and it is the reason the matcher is deterministic.

WHAT IS DELIBERATELY NOT HERE

- **`prepare_application`.** It fills an eleven-field form. Reading a form down
  a phone line, field by field, is worse than every alternative — including
  saying "I have sent it to your WhatsApp" and reading out a handoff code,
  whose alphabet already omits O/0 and I/1/L precisely so it can be spoken.
- **Retrieval-and-synthesis over scheme prose.** There is no vector store in
  this codebase and none belongs on this path. "Am I eligible?" answered by a
  model reading eligibility text is precisely the failure this system exists to
  prevent, and on a call it is worse than on the web: there is no screen showing
  the source sentence next to the claim. The caller cannot check. They just hear
  a confident voice telling them they qualify.
- **Recording.** Decided, not defaulted: calls are not recorded. See
  `RECORDING_POLICY` below.

WHAT THE PROVIDER SENDS US

Each tool is configured in the provider's dashboard with its own `server.url`,
so the tool name is in the path and the body is the provider's envelope:

    {"message": {"type": "tool-calls",
                 "toolCallList": [{"id": "...", "name": "...",
                                   "arguments": {...}}],
                 "call": {"customer": {"number": "+91..."}}}}

and it wants back:

    {"results": [{"toolCallId": "...", "result": "..."}]}

`result` is a string, so it carries compact JSON: `say` is the spoken line and
`detail` is there for anything the model wants to read out at length.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import inspect
import json
import logging
import re
import time
from typing import Any, Mapping, Optional

from fastapi import APIRouter, HTTPException, Request

from src import handoff
from src import whatsapp_brain as brain
from src import whatsapp_consent as consent
from src import interview
from src.agent import TOOL_IMPLEMENTATIONS
from src.config import get_settings
from src.discovery import Facets, discover

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


# ---------------------------------------------------------------------------
# Policy, written down rather than configured into existence
# ---------------------------------------------------------------------------

#: Calls are not recorded. Task 3 of the handoff asks for this to be decided and
#: written down rather than left to a default, so: decided. No audio is captured,
#: stored or forwarded by this service, which is why there is no consent script
#: for recording anywhere in this module — there is nothing to consent to.
#:
#: Turning this on is not a config change. It needs a spoken notice in all
#: thirteen languages BEFORE the first word is captured, a retention period, and
#: a deletion path. `test_voice.py` asserts it is off so that flipping it
#: silently is not possible.
RECORDING_POLICY = "none"

#: Never say these aloud and never ask for them. The fraud pattern this audience
#: suffers most is a phone call asking for exactly these, and a genuine service
#: that asks the same questions teaches people the scam is normal.
NEVER_ASK = ("aadhaar number", "bank account number", "otp", "pin", "password",
             "cvv", "upi pin")

#: A list of forty schemes is not a sentence. Everything spoken is cut to this;
#: `detail` keeps the rest for a caller who asks to hear more.
SPOKEN_ITEMS = 3


# ---------------------------------------------------------------------------
# Authentication
#
# These routes run the matching engine. An unauthenticated endpoint that does
# that for anyone who finds the URL is not acceptable, and it is doubly not
# acceptable while nothing else in this API has auth in front of it — a new
# public surface is the wrong thing to add at that moment.
#
# The pattern is `src/meta_whatsapp.py:88`: HMAC over the RAW body, compared
# with `compare_digest`, because comparing digests with `==` leaks how much of
# the digest matched through timing and the whole point of signing is lost if
# the check itself is exploitable.
# ---------------------------------------------------------------------------

def _fresh(timestamp: str, tolerance: int = 300) -> bool:
    """Whether a signed timestamp is recent enough to not be a replay.

    Absent or unparsable is treated as stale rather than fine: a provider that
    was configured to send a timestamp and then stopped is a signal, not a
    convenience.
    """
    try:
        sent = float(timestamp)
    except (TypeError, ValueError):
        return False
    # Milliseconds, as every provider here sends them, but seconds are accepted
    # so a correct integration is never rejected over a unit.
    if sent > 1e11:
        sent /= 1000.0
    return abs(time.time() - sent) <= tolerance


def verify_request(raw: bytes, headers: Mapping[str, str]) -> bool:
    """Whether this request really came from our telephony provider.

    Two mechanisms, because the provider offers both and which one is available
    depends on how the credential was created in its dashboard:

    1. **HMAC-SHA256 over the raw body**, in a configurable header. Preferred,
       and the only one that also proves the body was not altered in flight.
    2. **A static shared secret**, sent as `X-Vapi-Secret` or as a bearer token.
       Weaker — it proves the sender knows a secret, not that the body is
       untouched — but it is what the legacy credential type sends.

    A request carrying a signature header that does not verify is rejected
    outright and never falls through to the weaker check, or the weaker check
    would become a way around the stronger one.
    """
    settings = get_settings()

    if not settings.voice_verify_signatures:
        logger.warning("Voice signature verification DISABLED — local testing only")
        return True

    secret = settings.vapi_webhook_secret
    if not secret:
        # Fail closed. An unsigned endpoint that runs the engine is worse than
        # an endpoint that is switched off, and this is the same call
        # `meta_whatsapp.verify_signature` makes for the same reason.
        logger.error("No VAPI_WEBHOOK_SECRET set — refusing voice webhooks")
        return False

    lowered = {key.lower(): value for key, value in headers.items()}

    signature = lowered.get(settings.vapi_signature_header.lower())
    if signature:
        timestamp = lowered.get(settings.vapi_timestamp_header.lower(), "")
        # Signed payload includes the timestamp when one is sent, which is what
        # makes replaying yesterday's valid request fail today.
        signed = f"{timestamp}.".encode() + raw if timestamp else raw
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        # Tolerate `sha256=` / `v1=` prefixes without requiring them.
        candidate = signature.split("=")[-1].strip()
        if not hmac.compare_digest(expected, candidate):
            logger.warning("Voice webhook signature did not verify")
            return False
        if timestamp and not _fresh(timestamp):
            logger.warning("Voice webhook signature was valid but stale")
            return False
        return True

    presented = lowered.get("x-vapi-secret", "")
    if not presented:
        auth = lowered.get("authorization", "")
        if auth.lower().startswith("bearer "):
            presented = auth[7:].strip()

    if not presented:
        logger.warning("Voice webhook carried no signature and no secret")
        return False

    return hmac.compare_digest(secret, presented)


async def _authenticate(request: Request) -> bytes:
    """Verify and return the raw body — raw, because the signature is over it.

    Parsing the JSON and re-serialising it changes the bytes and every signature
    fails, so the body is read first and parsed second. This is the mistake that
    cost a day on the WhatsApp webhook and it is worth not repeating.
    """
    raw = await request.body()
    if not verify_request(raw, request.headers):
        raise HTTPException(status_code=403, detail="Invalid signature")
    return raw


# ---------------------------------------------------------------------------
# The provider's envelope
# ---------------------------------------------------------------------------

def _message(raw: bytes) -> dict:
    try:
        payload = json.loads(raw or b"{}")
    except (json.JSONDecodeError, ValueError):
        return {}
    return (payload or {}).get("message") or {}


def _tool_calls(message: dict) -> list[dict]:
    """Every tool call in this request, normalised to `{id, name, arguments}`.

    Two shapes are accepted. `toolCallList` is what the current documentation
    shows; `toolCalls` with a nested `function` object is the OpenAI-compatible
    shape the same provider has also been observed to send. Reading both costs
    six lines and saves an outage on a version bump.
    """
    calls: list[dict] = []

    for entry in message.get("toolCallList") or []:
        if not isinstance(entry, dict):
            continue
        calls.append({
            "id": entry.get("id") or "",
            "name": entry.get("name") or "",
            "arguments": _arguments(entry.get("arguments")),
        })

    for entry in message.get("toolCalls") or []:
        if not isinstance(entry, dict):
            continue
        function = entry.get("function") or {}
        calls.append({
            "id": entry.get("id") or "",
            "name": function.get("name") or entry.get("name") or "",
            "arguments": _arguments(function.get("arguments")),
        })

    return calls


def _arguments(value: Any) -> dict:
    """Arguments as a dict, however they arrived.

    A model serialises a nested object as a JSON STRING often enough that it
    cannot be treated as an exception — `src/agent.py:_clean_args` exists for
    the same reason. Parsed rather than rejected, because the content is right
    and only the envelope is wrong.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def caller_number(message: dict) -> str:
    """The number that rang us, which is the key to everything we remember.

    It is the only identifier spanning WhatsApp and a call, and the only one
    somebody hands over by their own action. Normalised to bare digits so that
    `+91 90000 00201`, `+919000000201` and `919000000201` are one person rather
    than three.
    """
    call = message.get("call") or {}
    customer = call.get("customer") or message.get("customer") or {}
    raw = str(customer.get("number") or "")
    return "".join(character for character in raw if character.isdigit())


def _results(calls: list[dict], produce) -> dict:
    """Run each call through `produce` and wrap it the way the provider wants.

    One failing tool must not fail the batch. A caller hearing "I could not look
    that up" for one thing is recoverable; a 500 is the assistant going silent
    mid-sentence, which is not.
    """
    out = []
    for call in calls:
        try:
            spoken, detail = produce(call)
        except Exception:                                    # noqa: BLE001
            logger.exception("Voice tool %s failed", call.get("name"))
            spoken, detail = ("I could not look that up just now.", {})
        out.append({
            "toolCallId": call.get("id") or "",
            "result": json.dumps({"say": spoken, "detail": detail},
                                 ensure_ascii=False, default=str),
        })
    return {"results": out}


# ---------------------------------------------------------------------------
# Which tools a phone call may reach
# ---------------------------------------------------------------------------

#: Tier 1 — a call is useless without these.
TIER_1 = ("find_schemes", "check_scheme_eligibility", "find_offices")

#: Tier 2 — worth having once Tier 1 is solid.
TIER_2 = ("lookup_scheme", "search_schemes", "price_loan", "corpus_stats")

#: Built here rather than wrapped, because they have no web equivalent.
NATIVE = ("next_question", "answer_question", "answer_faq", "resume_from_web")

#: Named so the refusal is explicit and testable rather than an absence someone
#: later reads as an oversight and "fixes".
REFUSED = {
    "prepare_application":
        "I can fill the form, but not down the phone — it has eleven fields. "
        "I will send it to your WhatsApp on this number instead.",
}

ALLOWED = set(TIER_1) | set(TIER_2) | set(NATIVE)


def _shorten(payload: dict) -> dict:
    """Cut a payload down to what is bearable read aloud.

    The counts stay whole — they are the answer — and only the enumerations are
    trimmed. A caller who wants the fourth scheme can ask for it.
    """
    trimmed = dict(payload)
    for key in ("top_matches", "matches", "offices", "partners", "results",
                "items", "schemes"):
        value = trimmed.get(key)
        if isinstance(value, list) and len(value) > SPOKEN_ITEMS:
            trimmed[key] = value[:SPOKEN_ITEMS]
            trimmed[f"{key}_spoken"] = SPOKEN_ITEMS
            trimmed[f"{key}_total"] = len(value)
    return trimmed


def run_tool(name: str, arguments: dict) -> tuple[str, dict]:
    """One tool, called exactly the way the web calls it.

    Wrapping `TOOL_IMPLEMENTATIONS` rather than reimplementing matching is the
    whole point: it is what stops the voice channel and the web channel drifting
    into two different answers to the same question, which is the kind of bug
    nobody finds until a person is told two different things.

    `cards` is discarded. It is the interface's half of the pair and there is no
    interface here.
    """
    if name in REFUSED:
        return REFUSED[name], {"refused": name}

    implementation = TOOL_IMPLEMENTATIONS.get(name)
    if implementation is None:
        return "I do not have a way to look that up.", {"unknown_tool": name}

    payload, _cards, summary = implementation(
        **_accepted(implementation, _arguments(arguments)))
    return summary, _shorten(payload if isinstance(payload, dict) else {})


def _accepted(implementation, arguments: dict) -> dict:
    """Only the arguments this particular tool actually takes.

    Two things arrive that a tool has never heard of. We fold in everything the
    caller has ever told us, and `Facets` carries twenty-one fields while
    `_tool_find_schemes` takes ten — so a caller who once said they were widowed
    would otherwise crash the lookup with an unexpected keyword. And a model
    invents argument names, which is a bad reason for a person to hear "I could
    not look that up".

    Dropping silently is right here: a tool that does not ask about marital
    status is not made better by being told. What it does ask about is
    unaffected.
    """
    try:
        accepts = inspect.signature(implementation).parameters
    except (TypeError, ValueError):                          # pragma: no cover
        return dict(arguments)
    return {key: value for key, value in arguments.items() if key in accepts}


# ---------------------------------------------------------------------------
# The adaptive interview
#
# `src/interview.py` picks the single most informative next question given what
# is still in play. On the web that is a nicety — twelve form fields could be
# shown at once. On a phone it is the only workable shape, because you can ask
# one question at a time and every extra question is a person deciding to hang
# up. It is the piece that makes a call genuinely better than the website rather
# than a worse copy of it.
# ---------------------------------------------------------------------------

#: Which questions have been put to this number, for the life of this process.
#:
#: Deliberately NOT persisted, and deliberately not in `user_context`. What a
#: person told us is durable — their state does not change because they hung up.
#: Which questions they were asked is a property of one call, and restoring it
#: days later would silently stop the interview ever offering a question they
#: once skipped. This is the same distinction `_EPHEMERAL_CONTEXT_KEYS` draws in
#: `whatsapp_brain.py:302`, kept local so that module does not have to change.
_ASKED: dict[str, set[str]] = {}

#: Session-scoped, so never written down. `categories` is what someone is
#: looking for today, not a fact about them — carrying it into next month's call
#: would silently filter that conversation to the last one's subject.
_SESSION_FACETS = frozenset({"categories"})

#: The facet fields worth carrying between channels — the ones that answer "who
#: is this person", which is what makes a returning caller not have to say it
#: all again.
#:
#: Derived from `discovery.Facets` rather than listed by hand. A hand-written
#: list was wrong within an hour of being written: it omitted `marital_status`,
#: `employment_status`, `residence`, `minority` and `land_acres`, so a caller
#: could answer "I am a widow", have it recorded against the matcher for that
#: one lookup, and be asked again on the next call. Anything the interview can
#: ask, this can keep.
DURABLE_FACETS = tuple(
    field.name for field in dataclasses.fields(Facets)
    if field.name not in _SESSION_FACETS
)


def known_facets(number: str) -> Facets:
    """What we already know about this caller, as the matcher wants it.

    Read from the same `user_context` the website and WhatsApp write to. A caller
    who has used WhatsApp is recognised — same number, same state, same caste,
    same language — without being asked again. That is the point of the feature,
    and the easiest thing in this phase to get right, because the table is
    already there.
    """
    stored = brain._CONTEXT.get(number) or {}
    facets = Facets()
    for field in DURABLE_FACETS:
        value = stored.get(field)
        if value not in (None, "", []):
            setattr(facets, field, value)
    return facets


def _remember_facets(number: str, facets: Facets) -> None:
    """Write the durable half back where every channel can read it."""
    for field in DURABLE_FACETS:
        value = getattr(facets, field, None)
        if value not in (None, "", []):
            brain._CONTEXT[number][field] = value


def _candidates(facets: Facets) -> set[str]:
    """The schemes still in play, which is what decides the next question.

    A corpus read per turn, and that is the price of the question depending on
    the answers — a precomputed order would be a fixed wizard wearing a
    different hat. A missing or half-written corpus ends the interview rather
    than the call.
    """
    try:
        result = discover(facets, limit=5000, include_not_matched=False)
        return {match.slug for match in result.matches}
    except Exception:                                        # noqa: BLE001
        logger.warning("Voice interview could not read the corpus", exc_info=True)
        return set()


def next_question(number: str) -> tuple[str, dict]:
    """The one question worth asking this caller now.

    Returns the question's own English prompt and its options. Translating it is
    the speaking model's job — it already has the caller's language — and the
    prompt text here is the same string the web asks, so the two channels ask
    the same question rather than two questions that resemble each other.
    """
    facets = known_facets(number)
    asked = _ASKED.setdefault(number, set())

    candidates = _candidates(facets)
    question = interview.next_question(candidates, asked) if candidates else None

    if question is None:
        return ("I have enough to look. Shall I tell you what you are entitled to?",
                {"finished": True, "asked": sorted(asked)})

    asked.add(question.id)
    return (question.fallback_prompt, {
        "finished": False,
        "question_id": question.id,
        "prompt": question.fallback_prompt,
        "options": [option.label for option in question.options][:8],
        "skippable": True,
        "asked_count": len(asked),
        "max_questions": interview.MAX_QUESTIONS,
    })


def answer_question(number: str, question_id: str, answer: str) -> tuple[str, dict]:
    """Record one spoken answer, or ask for it again.

    `interview.coerce` returning None means "ask again", never "skip". On a call
    that distinction matters more than anywhere else: a misheard answer recorded
    as a skip produces results that do not reflect what the person said, and
    there is no screen for them to catch it on. So an unreadable answer puts the
    question back rather than moving on.

    A genuine skip costs the caller precision and nothing else — `discovery` is
    built on "absence is not negation", so an unanswered question can never
    exclude a scheme. Saying so is what makes it safe to ask about caste or
    disability at all.
    """
    question = interview.BY_ID.get(question_id)
    if question is None:
        return "I lost track of that question. Let me ask again.", {"retry": True}

    asked = _ASKED.setdefault(number, set())
    spoken = (answer or "").strip()

    if spoken.lower() in ("skip", "pass", "no comment", "prefer not to say",
                          "don't want to say", "dont want to say"):
        asked.add(question.id)
        return ("That is fine — skipping costs you nothing.",
                {"skipped": question.id})

    value = interview.coerce(question, spoken)
    if value is None:
        # Not recorded as asked: an unreadable answer must come back round.
        asked.discard(question.id)
        return ("I did not catch that — could you say it again?",
                {"retry": True, "question_id": question.id,
                 "prompt": question.fallback_prompt})

    facets = known_facets(number)
    interview.apply_answer(facets, question, value)
    _remember_facets(number, facets)
    asked.add(question.id)

    return ("Got it.", {"question_id": question.id, "recorded": value,
                        "asked_count": len(asked)})


# ---------------------------------------------------------------------------
# The published FAQs
#
# 52,394 question-and-answer pairs across 4,721 of 4,736 schemes, written by the
# government and phrased as questions people actually ask. For a voice channel
# it is the best-shaped content in the corpus — it is already a spoken answer to
# a spoken question.
#
# QUOTED, NEVER SYNTHESISED. This returns the scheme's own published sentence or
# it returns nothing. A model may read it out and may translate it; it may not
# compose a new answer from it, and if the corpus has no answer the correct
# reply is that we do not know and here is the office that will.
#
# They are English-only, and measured rather than assumed: myScheme's API does
# return a per-language FAQ block, but across 382 sampled pairs 100% of the
# QUESTIONS were translated and 0% of the ANSWERS were. So backfilling it the
# way the other fields are backfilled would produce a column that looks
# translated and is not — which on a call means a Hindi voice reading an English
# sentence, with no screen to fall back on. See docs/SPIKE-voice-vapi.md.
#
# Until the per-language questions are backfilled, matching is over the English
# ones, and the answer is flagged for the speaking model to translate aloud and
# to say that it is translating.
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "what", "is", "the", "a", "an", "of", "for", "to", "in", "on", "and", "or",
    "how", "do", "does", "can", "i", "my", "me", "are", "be", "this", "that",
    "under", "it", "if", "there", "any", "will", "with", "get", "am",
})


def _words(text: str) -> set[str]:
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in (text or ""))
    return {w for w in cleaned.lower().split() if w and w not in _STOPWORDS}


def answer_faq(slug: str, question: str, language: str = "en") -> tuple[str, dict]:
    """The scheme's own published answer to the nearest published question.

    Ranked by word overlap rather than by a model. It is a set intersection over
    a handful of strings, it costs nothing, and — the part that matters — it
    cannot invent a question that was never asked or an answer that was never
    published.

    Returns no answer rather than a poor one. "We do not know, and here is who
    does" is a true sentence; a confidently-read near-miss is not.
    """
    from src.discovery import open_corpus

    connection = open_corpus()
    if connection is None:
        return ("I cannot reach the scheme records just now.", {"available": False})

    try:
        row = connection.execute(
            "SELECT name, faqs FROM schemes WHERE slug = ?", (slug,)).fetchone()
    finally:
        connection.close()

    if row is None:
        return ("I do not have that scheme.", {"found": False, "slug": slug})

    try:
        pairs = json.loads(row["faqs"] or "[]")
    except (json.JSONDecodeError, TypeError):
        pairs = []
    pairs = [p for p in pairs if isinstance(p, dict) and p.get("answer")]

    if not pairs:
        return ("That scheme has no published questions and answers.",
                {"found": True, "slug": slug, "pairs": 0})

    asked = _words(question)
    best, score = None, 0
    for pair in pairs:
        overlap = len(asked & _words(pair.get("question") or ""))
        if overlap > score:
            best, score = pair, overlap

    if best is None or score < 1:
        # Deliberately not "here is the closest one we have". A near-miss read
        # in a confident voice is indistinguishable, to the listener, from an
        # answer — and they cannot see the question it actually answers.
        return ("The scheme's published questions do not cover that. "
                "I can tell you which office will know.",
                {"found": True, "slug": slug, "matched": False,
                 "pairs": len(pairs), "suggest": "find_offices"})

    answer = (best.get("answer") or "").strip()
    return (answer, {
        "found": True,
        "matched": True,
        "slug": slug,
        "scheme": (row["name"] or "").strip(),
        "question": (best.get("question") or "").strip(),
        "answer": answer,
        "quoted": True,
        "source_language": "en",
        # The speaking model translates and says so. Acceptable here and only
        # here: this is quoted content, not a decision about a person. An
        # eligibility verdict is never translated — it is computed.
        "translate_aloud": language not in ("en", "", None),
        "say_it_is_a_translation": language not in ("en", "", None),
    })


# ---------------------------------------------------------------------------
# Carrying a website session onto the call
#
# A caller who has used WhatsApp is already recognised — the phone number is the
# key and `user_context` holds what they told us, whichever channel taught us.
# Somebody who has only used the WEBSITE is a different case: the site never
# learns a phone number, so there is nothing to key on until they ring, and by
# then the browser session is somewhere else entirely.
#
# `src/handoff.py` already solved this for WhatsApp, and solved it in a shape
# that was clearly meant to end up here: the code's alphabet omits O/0 and
# I/1/L because "people read these aloud". It has simply never been read aloud.
# This is the tool that lets them.
# ---------------------------------------------------------------------------

#: A transcriber writes digits as words about as often as as numerals, and the
#: code's alphabet contains 2-9. Nothing here guesses at letters: the alphabet
#: was chosen to avoid the pairs that are actually confusable by ear.
_SPOKEN_DIGITS = {
    "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
    "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9",
}

#: The separator, when it is said out loud rather than heard as punctuation.
#:
#: This one is not politeness, it is a correctness fix. D, A, S and H are all
#: valid code characters, so "Y S dash A B C two three four" flattened to
#: YSDASHABC234 and read back as `YS-DASHAB` — a wrong code that looks exactly
#: like a right one, which the caller is then told has expired. Being told your
#: code is expired when it was misheard is worse than being asked to repeat it.
_SPOKEN_SEPARATORS = ("DASH", "HYPHEN", "MINUS")


def spoken_code(said: str) -> Optional[str]:
    """Read a handoff code out of something a person said down a phone.

    `handoff.find` wants the literal `YS-` and the exact six characters, which
    is right for a pasted message and wrong for speech: what arrives is "Y S
    dash A B C two three four", or "ys abc234", or the same with the dash heard
    as a word. So the text is flattened to letters and digits first and the
    marker looked for inside it.

    Returns the canonical `YS-XXXXXX`, so everything downstream — including
    `handoff.claim` — sees exactly what the website minted.
    """
    if not said:
        return None

    text = said.upper()
    for word, digit in _SPOKEN_DIGITS.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    for word in _SPOKEN_SEPARATORS:
        text = re.sub(rf"\b{word}\b", " ", text)

    squashed = re.sub(r"[^A-Z0-9]", "", text)
    marker = handoff.PREFIX
    for match in re.finditer(marker, squashed):
        body = squashed[match.end():match.end() + handoff.LENGTH]
        if len(body) == handoff.LENGTH and all(c in handoff.ALPHABET for c in body):
            return f"{marker}-{body}"
    return None


async def resume_from_web(number: str, said: str) -> tuple[str, dict]:
    """Redeem a code read out on the call, and carry the session onto it.

    Someone who answered six questions on the website and then rang us must not
    be asked their state again — being asked twice is the clearest possible
    signal that nobody was listening, and on a call it costs them minutes they
    are paying for.

    A code that is unknown, spent or stale is not an error worth explaining. The
    caller does not know what a handoff code is; they know they used the website.
    So the reply moves on and the interview simply starts from what we know.
    """
    code = spoken_code(said)
    if code is None:
        return ("I did not catch that code — could you read it again, "
                "one character at a time?",
                {"retry": True, "reason": "unreadable"})

    entry = await handoff.claim(code)
    if entry is None:
        return ("That code has already been used or has expired. "
                "No matter — I can ask you directly.",
                {"resumed": False, "code": code, "reason": "expired_or_spent"})

    carried = {key: value for key, value in (entry.context or {}).items()
               if value not in (None, "", [])}
    if number and carried:
        brain._CONTEXT[number].update(carried)

    logger.info("Call from %s resumed from the website (%s)",
                (number or "unknown")[:6] + "…",
                ", ".join(sorted(carried)) or "no context")

    return ("I have what you told the website — I will not ask you that again.",
            {"resumed": True, "code": code, "carried": sorted(carried)})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

async def _prepare(number: str) -> bool:
    """Load what we know about this caller. False when nothing may be stored.

    Somebody who sent STOP has asked to be left alone. Ringing us is not a
    retraction of that — it is a person who needs help now — so the call is
    answered in full and simply leaves no trace. Refusing to help them would
    punish them for a preference about messages.
    """
    if not number:
        return False
    if consent.is_loaded() and consent.has_opted_out(number):
        logger.info("Caller %s has opted out — answering, storing nothing",
                    number[:6] + "…")
        return False
    await brain.load_context(number)
    return True


@router.post("/tools/{name}")
async def call_tool(name: str, request: Request) -> dict:
    """One tool, called by the voice model mid-conversation.

    Thin, fast and deterministic. Budget is p95 under ~300 ms; the lookups are
    about 110 ms and the rest is envelope.
    """
    raw = await _authenticate(request)

    if name not in ALLOWED and name not in REFUSED:
        raise HTTPException(status_code=404, detail="No such tool")

    message = _message(raw)
    calls = _tool_calls(message)
    number = caller_number(message)
    storable = await _prepare(number)

    # A tool invoked by name in the path with no envelope is still a valid call —
    # it is how the endpoint is tested and how a provider that sends bare
    # arguments would reach it.
    if not calls:
        calls = [{"id": "", "name": name, "arguments": _arguments(
            (message.get("arguments") if isinstance(message, dict) else None))}]

    # The one tool that touches the database, so the one that cannot run inside
    # the synchronous dispatcher below. Done first, and its answer handed to it.
    resumed: dict[str, tuple[str, dict]] = {}
    if name == "resume_from_web":
        for call in calls:
            said = str((call.get("arguments") or {}).get("code") or "")
            resumed[call.get("id") or ""] = await resume_from_web(number, said)

    def produce(call: dict) -> tuple[str, dict]:
        arguments = call.get("arguments") or {}

        if name == "resume_from_web":
            return resumed[call.get("id") or ""]
        if name == "next_question":
            return next_question(number)
        if name == "answer_question":
            return answer_question(number,
                                   str(arguments.get("question_id") or ""),
                                   str(arguments.get("answer") or ""))
        if name == "answer_faq":
            # The caller's own language, from whichever channel taught us —
            # so a Hindi speaker is told the quote is a translation without the
            # model having to work out which language it is speaking.
            return answer_faq(
                str(arguments.get("slug") or ""),
                str(arguments.get("question") or ""),
                str(arguments.get("language")
                    or brain.language_if_known(number) or "en"),
            )

        # Everything the caller already told us, folded under what they just
        # said — so `find_schemes` on a call knows their state without the model
        # having to repeat it back to us as an argument.
        merged = {field: value for field, value in
                  vars(known_facets(number)).items()
                  if value not in (None, "", []) and field in DURABLE_FACETS}
        merged.update({key: value for key, value in arguments.items()
                       if value not in (None, "")})
        return run_tool(name, merged)

    payload = _results(calls, produce)

    if storable:
        await brain.save_context(number)

    return payload


@router.post("/events")
async def call_event(request: Request) -> dict:
    """Everything the provider reports that is not a tool call.

    Only two events are acted on. `status-update` marks the end of a call so the
    interview state for that number is dropped — a call is a session, and the
    next one should not inherit a half-finished question list. Everything else is
    acknowledged and ignored, because a provider that gets a non-200 retries, and
    a retried webhook is a second answer to a question already answered.
    """
    raw = await _authenticate(request)
    message = _message(raw)
    kind = message.get("type") or ""
    number = caller_number(message)

    if kind in ("status-update", "end-of-call-report", "hang"):
        status = (message.get("status") or message.get("endedReason") or "")
        if kind != "status-update" or status in ("ended", "forwarding"):
            _ASKED.pop(number, None)
            logger.info("Call with %s ended (%s)", number[:6] + "…", status or kind)

    return {"received": True}


@router.get("/health")
async def voice_health() -> dict:
    """What is configured, without saying what any of it is.

    The commonest way this integration is broken is a secret that was never set,
    and that is invisible until a real call produces a 403 that the provider
    reports as "assistant did not respond".
    """
    settings = get_settings()
    return {
        "status": "ok",
        "signature_verification": settings.voice_verify_signatures,
        "secret_configured": bool(settings.vapi_webhook_secret),
        "recording": RECORDING_POLICY,
        "tools": {"tier_1": list(TIER_1), "tier_2": list(TIER_2),
                  "native": list(NATIVE), "refused": sorted(REFUSED)},
    }
