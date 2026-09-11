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
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 6
PREFIX = "YS"

TTL_SECONDS = 30 * 60

# In a table now. It used to be this dict alone, with a note saying it needed
# one "because a restart mid-handoff strands whoever was crossing at that
# moment" — which is a person who answered six questions on the website, tapped
# through to WhatsApp, and arrives to be asked their state again.
#
# The dict survives as a same-process fast path and as the fallback when the
# database is unreachable: a handoff that works until the next restart is worth
# more than one that fails now.
_PENDING: dict[str, "Handoff"] = {}


@dataclass
class Handoff:
    context: dict
    history: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.monotonic)


def _expired(entry: "Handoff") -> bool:
    return (time.monotonic() - entry.created) > TTL_SECONDS


def _cutoff_iso() -> str:
    """The wall-clock instant before which a stored handoff is stale.

    Rows carry wall-clock time because the monotonic clock the in-memory path
    uses resets to zero on restart — every stored handoff would read as brand
    new, and a code from last week would still redeem.
    """
    return (datetime.now(timezone.utc)
            - timedelta(seconds=TTL_SECONDS)).isoformat()


def _sweep() -> None:
    for code in [c for c, e in _PENDING.items() if _expired(e)]:
        _PENDING.pop(code, None)


async def create(context: Optional[dict] = None,
                 history: Optional[list[dict]] = None) -> str:
    """Park a conversation and return the code that redeems it."""
    _sweep()
    code = PREFIX + "-" + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    entry = Handoff(
        context=dict(context or {}),
        # Only the last few turns. The point is continuity, not a transcript,
        # and a long history in a prompt costs more than it is worth here.
        history=list(history or [])[-6:],
    )
    _PENDING[code] = entry

    try:
        from src.database import get_connection, put_handoff, sweep_handoffs
        db = await get_connection()
        try:
            await put_handoff(db, code, json.dumps(entry.context),
                              json.dumps(entry.history))
            await sweep_handoffs(db, _cutoff_iso())
        finally:
            await db.close()
    except Exception:
        # The in-memory copy still works for this process. A handoff that
        # survives until the next restart beats one that fails right now.
        logger.exception("Could not persist handoff %s", code)

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


async def claim(code: str) -> Optional[Handoff]:
    """Redeem a code, once. Returns None if unknown, used or stale.

    The database is consulted FIRST, and its DELETE ... RETURNING is what makes
    "once" true across processes. Checking memory first would let two workers
    both serve the same code, since each has its own dict.
    """
    _sweep()
    try:
        from src.database import get_connection, take_handoff
        db = await get_connection()
        try:
            row = await take_handoff(db, code)
        finally:
            await db.close()
    except Exception:
        logger.exception("Could not read handoff %s", code)
        row = None

    if row is not None:
        context_json, history_json, created_at = row
        _PENDING.pop(code, None)          # this process's copy is spent too
        if created_at < _cutoff_iso():
            return None
        logger.info("Handoff %s claimed", code)
        return Handoff(context=json.loads(context_json or "{}"),
                       history=json.loads(history_json or "[]"))

    # Nothing stored — either the write failed earlier or the database is down.
    entry = _PENDING.pop(code, None)
    if entry is None or _expired(entry):
        return None
    logger.info("Handoff %s claimed from memory", code)
    return entry


def strip(text: str, code: str) -> str:
    """The message without the code, so the assistant answers the question.

    Someone who sends "YS-4H7K I need help with the loan" is asking about the
    loan; the code is plumbing and should never reach the model as though it
    were part of what they said.
    """
    cleaned = text.replace(code, " ").replace(code.lower(), " ")
    return " ".join(cleaned.split()).strip()
