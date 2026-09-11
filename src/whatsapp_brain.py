"""
What WhatsApp says back — the same engine the website uses.

Until now WhatsApp ran its own LangGraph flow that asked "business loan or
education loan?", which is the failure the web chat already had: most of the
4,736 schemes are not loans, and a widow asking about a pension was offered a
choice between two kinds of borrowing. One brain, two channels, or the channel
that reaches the most people stays the worst one.

Two modes, same as the web:

- With a model key, the agent answers open questions using its seven tools.
- Without one, the scripted flow in `chat.py` asks the need-first questions.

The hard part here is not the answer, it is the rendering. WhatsApp has no
cards: everything a person sees is one text message. So the structured results
the engine returns are flattened into plain lines, in WhatsApp's own markup —
which is *single* asterisks for bold, not Markdown's double. Getting that wrong
shows literal asterisks to someone who may already be reading with difficulty.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from typing import Deque

from src.agent import is_available as agent_available, respond as agent_respond
from src.paths import strip_media_paths
from src.chat import turn as scripted_turn
from src import handoff
from src import whatsapp_consent as consent
from src.i18n import detect_language

logger = logging.getLogger(__name__)

# WhatsApp's own limit is 1600 characters, but that is not the limit that
# matters. The client folds a long message behind a "Read more" link at roughly
# 700, and a folded answer is an unread answer — the first version of this shipped
# a 1,400-character wall whose actual advice was below the fold. This is a hard
# backstop; the real work is done by the prompt, which asks for about six lines.
MAX_MESSAGE_CHARS = 800

# The last few turns per phone number, so the assistant can follow a thread.
# In memory on purpose: it is small, it is not worth a schema, and losing it on
# restart costs a person one repeated sentence rather than their application.
_HISTORY: dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=8))

# What we have learned about each number, so it is not asked twice.
_CONTEXT: dict[str, dict] = defaultdict(dict)


def remember_language(user_id: str, text: str) -> str:
    """Detect and keep the language, so later messages stay in it.

    A person writes in Odia once; every reply after that should be in Odia even
    when they answer a yes/no question with a digit.

    WhatsApp has no language picker, so an undetected script means English —
    stated rather than left to the model, which given an Indian phone number
    will otherwise answer "hello" in Hindi. Writing one message in any of the
    thirteen scripts switches it, and it stays switched.
    """
    detected = detect_language(text)
    if detected:
        _CONTEXT[user_id]["language"] = detected
    return _CONTEXT[user_id].get("language", "en")


def known_language(user_id: str) -> str:
    """The language this number has been writing in, for transcription.

    Telling the transcriber which language to expect beats letting it guess,
    especially for a sentence that mixes a Tamil question with an English
    scheme name.
    """
    return _CONTEXT[user_id].get("language", "en")


def language_if_known(user_id: str) -> str | None:
    """The same thing, but honest about not knowing yet.

    `known_language` answers "en" for someone we have never heard from, which
    is the right default for writing a reply and the wrong one for listening to
    a voice note: it tells the transcriber to expect English from a person who
    may be speaking Tamil. None means "work it out", and the transcriber is
    better at that than we are.
    """
    return _CONTEXT[user_id].get("language")


def remember_detected_language(user_id: str, language: str | None) -> None:
    """Learn the language from a voice note, not just from a typed script.

    Someone whose first message is spoken has told us just as clearly as
    someone who typed — and they are more likely to be the person who cannot
    type in their own script at all, so this is the case that matters most.
    """
    if language and language != _CONTEXT[user_id].get("language"):
        logger.info("Language for %s set to %s from speech", user_id[:8], language)
        _CONTEXT[user_id]["language"] = language


def to_whatsapp_markup(text: str) -> str:
    """Markdown as the model writes it, to WhatsApp as it renders it.

    WhatsApp uses *one* asterisk for bold and has no headings or links syntax.
    Left alone, `**Micro Finance Scheme**` arrives with the asterisks visible.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text, flags=re.S)   # bold
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)           # headings
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.M)        # bullets
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", text)   # links
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clip(text: str) -> str:
    """Trim to one message, on a line break rather than mid-word."""
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    cut = text[:MAX_MESSAGE_CHARS]
    boundary = max(cut.rfind("\n"), cut.rfind(". "))
    return (cut[:boundary] if boundary > MAX_MESSAGE_CHARS * 0.6 else cut).rstrip() + "…"


def take_pending_map(user_id: str) -> str | None:
    """The map this reply produced, if any — and only once.

    Popped rather than read, so a map is never sent twice for one lookup and
    never trails a later message it has nothing to do with.
    """
    return _CONTEXT[user_id].pop("pending_map", None)


def render_cards(cards: list[dict]) -> str:
    """Structured results as lines someone can read on a phone.

    Deliberately terse. This is the same data the website shows as cards, and a
    card's worth of labels becomes noise when it is flattened into a message.
    """
    lines: list[str] = []

    for card in cards:
        kind = card.get("kind")

        if kind == "matches":
            targeted, total = card.get("targeted", 0), card.get("total", 0)
            if targeted:
                lines.append(f"*{targeted}* of *{total}* are meant for someone like you.")
            for item in (card.get("items") or [])[:4]:
                reasons = ", ".join(item.get("matched_on") or [])
                lines.append(f"• {item['name'].strip()}"
                             + (f" — matches on {reasons}" if reasons else ""))

        elif kind == "scheme_list":
            for item in (card.get("items") or [])[:4]:
                lines.append(f"• {item['name'].strip()}")

        elif kind == "eligibility":
            verdict = card.get("verdict")
            head = "✅" if verdict != "NOT_MATCHED" else "❌"
            lines.append(f"{head} *{card.get('name')}*")
            if card.get("unmet"):
                lines.append(f"   Does not match on: {', '.join(card['unmet'])}")
            if card.get("unknown"):
                lines.append(f"   Still to check: {', '.join(card['unknown'])}")

        elif kind == "scheme":
            best = " (cheapest)" if card.get("best") else ""
            lines.append(f"*{card.get('name')}*{best}")
            lines.append(f"   {card.get('loan')} at {card.get('rate')}%")
            lines.append(f"   {card.get('instalment')} × {card.get('instalment_count')}"
                         f" · interest {card.get('interest')}")

        elif kind == "compare":
            lines.append(f"⚠️ {card.get('alt_label')} would take {card.get('alt_amount')}"
                         f" — you keep {card.get('saving')}.")

        elif kind == "partners":
            lines.append("*Where to go*")
            for item in (card.get("items") or [])[:3]:
                distance = item.get("distance_km")
                where = item.get("where", "")
                lines.append(f"• {item['name']} — {where}"
                             + (f", {distance} km" if distance is not None else ""))

        elif kind in ("whynot", "blocked"):
            for item in (card.get("items") or [])[:3]:
                lines.append(f"• {item['name']}: {item['reason']}")

        elif kind == "notice" and card.get("tone") == "warn":
            lines.append(f"⚠️ {card.get('body')}")

    return "\n".join(lines)


def _resume_from_web(user_id: str, text: str) -> str:
    """Redeem a handoff code, and return the message without it.

    Silent when there is no code, and silent when the code is stale or already
    used — a person who forwarded an old link should simply get a normal first
    conversation, not an error about a token they never knew existed.
    """
    code = handoff.find(text)
    if not code:
        return text

    entry = handoff.claim(code)
    if entry is None:
        logger.info("Handoff code from %s was unknown or expired", user_id[:8])
        return handoff.strip(text, code)

    carried = {k: v for k, v in (entry.context or {}).items()
               if v not in (None, "", [])}
    if carried:
        _CONTEXT[user_id].update(carried)
    for turn in entry.history or []:
        if turn.get("text"):
            _HISTORY[user_id].append({"role": turn.get("role", "user"),
                                      "text": turn["text"]})

    # The notice still goes out — crossing channels is not consent to the new
    # one — but everything they already told us comes with them.
    logger.info("Resumed %s from the website (%s)",
                user_id[:8], ", ".join(sorted(carried)) or "no context")
    return handoff.strip(text, code)


async def reply(user_id: str, text: str) -> str:
    """One WhatsApp turn: whatever they said, whatever we say back.

    Returns "" when nothing should be sent — which happens only for someone who
    has opted out, and is the correct amount to say to them.
    """
    # Before anything else. STOP is not a feature to be reached after the
    # interesting code has run.
    gate = consent.check(user_id, text)
    if gate is not None:
        if gate:
            _HISTORY.pop(user_id, None)
            _CONTEXT.pop(user_id, None)
        return gate

    # A code from the website, redeemed before anything else looks at the
    # message. Someone who answered six questions on the site and then crossed
    # over must not be asked which state they live in — being asked again is
    # the clearest possible signal that nobody was listening.
    text = _resume_from_web(user_id, text)

    language = remember_language(user_id, text)

    # The notice goes out once, UNDER the first real answer rather than above
    # it. Making someone say a magic word before being helped is how you lose
    # the person this is for — and putting the notice first pushed the answer
    # behind WhatsApp's "Read more" fold, which loses them just as effectively.
    footer = ""
    if not _CONTEXT[user_id].get("greeted"):
        _CONTEXT[user_id]["greeted"] = True
        footer = f"\n\n{consent.notice(language)}"

    if agent_available():
        answer = await _agent_reply(user_id, text, language)
        if answer:
            return _clip(answer) + footer
        # The agent stood aside — no key, or every model's quota is spent. The
        # scripted flow still works, and a person mid-question should not be
        # told to come back tomorrow.
        logger.info("Agent unavailable for %s, falling back to the script", user_id[:8])

    return _clip(await _scripted_reply(user_id, text, language)) + footer


# Bookkeeping that belongs to this module, not to the model. Sending it would
# put "last_options" in the prompt as though it were a fact about the person.
_PRIVATE_CONTEXT_KEYS = {"last_options", "language"}


def _agent_context(user_id: str) -> dict:
    return {
        key: value
        for key, value in _CONTEXT[user_id].items()
        if key not in _PRIVATE_CONTEXT_KEYS and value not in (None, "", [])
    }


async def _agent_reply(user_id: str, text: str, language: str | None) -> str:
    history = list(_HISTORY[user_id])
    result = await agent_respond(
        text, history=history, context=_agent_context(user_id), language=language,
        channel="whatsapp",
    )
    if not result.used_model:
        return ""

    # The cards are a FALLBACK, not a companion to the prose.
    #
    # On the website the model writes the judgement and the cards carry the
    # facts, so both belong. On WhatsApp there are no cards — the model has
    # been told to write the schemes into its own message — so appending them
    # printed the same four schemes twice in one bubble, once in the model's
    # sentences and once as a bulleted list underneath. Whichever the reader
    # believed, the other one made them doubt it.
    # A map, if the offices lookup drew one. Held aside rather than described:
    # the worker sends it as a second message once the text has landed, so the
    # answer arrives first and the picture confirms it.
    for card in result.cards:
        if card.get("kind") == "map" and card.get("url"):
            _CONTEXT[user_id]["pending_map"] = card["url"]
            break

    body = to_whatsapp_markup(result.text or "")
    # Stripped once, at the last point both branches pass through — the card
    # fallback renders paths too.
    message = strip_media_paths(body or render_cards(result.cards))
    if not message.strip():
        return ""

    _HISTORY[user_id].append({"role": "user", "text": text})
    _HISTORY[user_id].append({"role": "assistant", "text": result.text or ""})
    return _clip(message)


async def _scripted_reply(user_id: str, text: str, language: str | None) -> str:
    """The guided flow, with the phone number as the conversation thread."""
    result = await scripted_turn(
        user_id, resolve_numbered_choice(user_id, text), language=language,
    )

    parts = [m["text"] for m in result.get("messages", []) if m.get("text")]

    # Options become a numbered list, because WhatsApp has no buttons here and
    # "reply 2" is easier to type than a phrase in a script you dictate with.
    chips = result.get("chips") or []
    if chips:
        parts.append("\n".join(
            f"{index}. {chip['label']}" for index, chip in enumerate(chips, start=1)
        ))

    # The scripted flow draws maps too, and only the agent path was
    # keeping them — so a map the fallback rendered was written to disk
    # and then dropped on the floor.
    for card in result.get("cards") or []:
        if card.get("kind") == "map" and card.get("url"):
            _CONTEXT[user_id]["pending_map"] = card["url"]
            break

    cards = render_cards(result.get("cards") or [])
    if cards:
        parts.append(cards)

    return _clip(strip_media_paths("\n\n".join(part for part in parts if part).strip()))


def resolve_numbered_choice(user_id: str, text: str) -> str:
    """Turn "2" back into the option it stood for.

    People answer a numbered list with a number. The engine expects the value,
    so this translates before the message reaches it — and leaves anything that
    is not a bare number untouched, since "2 lakh" is an amount, not a choice.
    """
    stripped = text.strip()
    if not stripped.isdigit():
        return text
    options = _CONTEXT[user_id].get("last_options") or []
    index = int(stripped) - 1
    return options[index] if 0 <= index < len(options) else text


def remember_options(user_id: str, chips: list[dict]) -> None:
    _CONTEXT[user_id]["last_options"] = [chip["value"] for chip in chips]
