"""
Carrying a conversation from the website into WhatsApp.

Someone answers six questions on the site, gets their matches, and then wants
to carry on where they actually talk. Today that is a fresh start: the deep
link opens WhatsApp with a fixed sentence, and the first thing the assistant
does is ask which state they live in — which they answered four minutes ago.
Being asked again is the clearest possible signal that nobody was listening.

WhatsApp gives us nothing to hold onto. The deep link carries text and nothing
else; there are no parameters, no session, and the phone number is not known
until the person messages us. So the state has to travel inside the only thing
that crosses: the message body.

Hence a code. The website mints one, parks the context behind it, and puts it
in the prefilled message. The first WhatsApp message redeems it and the
assistant carries on knowing what it already knew.

DELIBERATELY SHORT-LIVED AND SINGLE-USE

The context holds what someone told the wizard — their state, their community,
sometimes their household income. That is not a credential, but it is theirs,
and a code that stays valid forever in a message anyone can forward is a way
of leaking it. Thirty minutes, one redemption, then gone.

The alphabet omits O/0 and I/1/L. People read these aloud and type them on a
phone keyboard, and a code that cannot be transcribed is worse than no code.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 6
PREFIX = "YS"

TTL_SECONDS = 30 * 60

# In memory on purpose, and flagged the same way the consent list is: it is
# small, it is short-lived, and losing it on restart costs someone one repeated
# question rather than their application. It still needs a table before this
# takes real traffic, because a restart mid-handoff strands whoever was
# crossing at that moment.
_PENDING: dict[str, "Handoff"] = {}


@dataclass
class Handoff:
    context: dict
    history: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.monotonic)


def _expired(entry: "Handoff") -> bool:
    return (time.monotonic() - entry.created) > TTL_SECONDS


def _sweep() -> None:
    for code in [c for c, e in _PENDING.items() if _expired(e)]:
        _PENDING.pop(code, None)


def create(context: Optional[dict] = None,
           history: Optional[list[dict]] = None) -> str:
    """Park a conversation and return the code that redeems it."""
    _sweep()
    code = PREFIX + "-" + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    _PENDING[code] = Handoff(
        context=dict(context or {}),
        # Only the last few turns. The point is continuity, not a transcript,
        # and a long history in a prompt costs more than it is worth here.
        history=list(history or [])[-6:],
    )
    logger.info("Handoff %s created (%d pending)", code, len(_PENDING))
    return code


def find(text: str) -> Optional[str]:
    """Pull a handoff code out of whatever someone actually sent.

    They may paste the prefilled sentence, or type just the code, or top-and-
    tail it with a greeting. Case is normalised because phone keyboards
    capitalise the first letter of a message on their own.
    """
    if not text:
        return None
    upper = text.upper()
    marker = PREFIX + "-"
    at = upper.find(marker)
    if at < 0:
        return None
    candidate = upper[at:at + len(marker) + LENGTH]
    body = candidate[len(marker):]
    if len(body) != LENGTH or any(ch not in ALPHABET for ch in body):
        return None
    return candidate


def claim(code: str) -> Optional[Handoff]:
    """Redeem a code, once. Returns None if unknown, used or stale."""
    _sweep()
    entry = _PENDING.pop(code, None)
    if entry is None:
        return None
    if _expired(entry):
        return None
    logger.info("Handoff %s claimed", code)
    return entry


def strip(text: str, code: str) -> str:
    """The message without the code, so the assistant answers the question.

    Someone who sends "YS-4H7K I need help with the loan" is asking about the
    loan; the code is plumbing and should never reach the model as though it
    were part of what they said.
    """
    cleaned = text.replace(code, " ").replace(code.lower(), " ")
    return " ".join(cleaned.split()).strip()
