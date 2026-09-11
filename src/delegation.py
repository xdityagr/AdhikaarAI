"""
A citizen handing their case to an operator, and being able to take it back.

This is the thing that makes storing a profile defensible at all. `profile.ts`
says a person's answers live on their own phone and go no further; the operator
panel needs them on a server so somebody at a CSC counter can fill a form. The
only honest bridge between those two facts is that the citizen hands the case
over themselves, deliberately, and can end it whenever they like.

So: no operator ever creates a case. They redeem a code the citizen gave them.

WHY NOT `handoff.py`

It reuses that module's alphabet, and nothing else, because the two mechanisms
only look alike:

                      web -> WhatsApp          citizen -> operator
  lifetime            30 minutes               a case, which is days
  redeemed by         anybody with the code    one named operator, recorded
  failure             silent, on purpose       loud, on purpose
  what it carries     conversation context     permission to act for someone
  ending it           it expires               the citizen revokes it

A handoff that stays valid for days, binds to nobody and fails quietly would be
a bad version of both. The alphabet IS worth sharing: it omits O/0 and I/1/L
because people read these aloud, and this code is read aloud across a desk.

The prefix differs so the two cannot be confused. A citizen who pastes a `YS-`
code at a counter gets a clear refusal rather than a mysterious one.

FAILURE IS LOUD HERE

`handoff.claim` returns None for unknown, used and stale alike — right for a
citizen who forwarded an old link, since the assistant simply carries on. An
operator with a person in front of them needs to know WHICH, because "already
claimed by someone else" and "the citizen revoked this" and "you typed it wrong"
lead to three different next actions.
"""

from __future__ import annotations

import enum
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.handoff import ALPHABET, LENGTH

logger = logging.getLogger(__name__)

#: Not `YS-`. See the docstring.
PREFIX = "YC"

#: How long an UNCLAIMED code stays good. Long enough to be written on a slip
#: of paper and taken to a counter tomorrow; short enough that a code in an old
#: message is not a way in. Once claimed, the case lives until it is closed or
#: revoked and this no longer applies.
CLAIM_HOURS = 24

#: What the citizen is agreeing to. Recorded on the row rather than assumed, so
#: that widening it later cannot silently re-interpret consent already given.
SCOPE = "file_on_my_behalf"


class Refusal(str, enum.Enum):
    """Why a code did not open a case. Each one is a different next action."""
    UNKNOWN = "unknown"            # mistyped, or never existed
    EXPIRED = "expired"            # made more than CLAIM_HOURS ago, unclaimed
    ALREADY_CLAIMED = "claimed"    # another operator holds it
    REVOKED = "revoked"            # the citizen took it back
    CLOSED = "closed"              # the case is finished


class DelegationError(Exception):
    """A claim that did not succeed, carrying which refusal it was."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.value)
        self.refusal = refusal


@dataclass(frozen=True)
class Case:
    """One citizen's case, as the operator holding it sees it."""
    case_id: str
    code: str
    #: What the citizen chose to share. Their answers, not their documents.
    context: dict
    #: The scheme this is about, when it is about one.
    scheme_slug: Optional[str]
    #: The language the citizen reads. An operator who speaks to them in the
    #: wrong one has undone most of the point of this product.
    language: str
    created_at: str
    claimed_by: Optional[str]
    claimed_at: Optional[str]
    closed_at: Optional[str]
    revoked_at: Optional[str]

    @property
    def live(self) -> bool:
        return not (self.closed_at or self.revoked_at)


def new_code() -> str:
    return PREFIX + "-" + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalise(text: str) -> Optional[str]:
    """A code out of whatever was typed, or None.

    Phone and desktop keyboards both capitalise unpredictably and people add
    spaces, so this is forgiving about everything except the alphabet itself.
    """
    if not text:
        return None
    upper = "".join(text.split()).upper()
    marker = PREFIX + "-"
    at = upper.find(marker)
    if at < 0:
        # Somebody typed only the six characters.
        body = upper[:LENGTH]
        if len(upper) == LENGTH and all(ch in ALPHABET for ch in body):
            return marker + body
        return None
    candidate = upper[at:at + len(marker) + LENGTH]
    body = candidate[len(marker):]
    if len(body) != LENGTH or any(ch not in ALPHABET for ch in body):
        return None
    return candidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claim_cutoff() -> str:
    """Before this instant, an unclaimed code is stale."""
    return (datetime.now(timezone.utc) - timedelta(hours=CLAIM_HOURS)).isoformat()


# ---------------------------------------------------------------------------
# The citizen's side
# ---------------------------------------------------------------------------

async def offer(context: Optional[dict] = None,
                scheme_slug: Optional[str] = None,
                language: str = "en",
                citizen_ref: Optional[str] = None) -> Case:
    """The citizen creates the code. Only they can.

    `citizen_ref` is their phone number when they came through WhatsApp, so a
    revocation can be honoured from the channel they are already using. It is
    absent for someone on the website, who revokes with the code itself — which
    is the only thing they hold.
    """
    from src.database import get_connection, put_case

    case_id, code, now = uuid.uuid4().hex, new_code(), _now()
    db = await get_connection()
    try:
        await put_case(db, case_id, code, json.dumps(dict(context or {})),
                       scheme_slug, language, citizen_ref, SCOPE, now)
    finally:
        await db.close()

    logger.info("Case %s offered", case_id)
    return Case(case_id=case_id, code=code, context=dict(context or {}),
                scheme_slug=scheme_slug, language=language, created_at=now,
                claimed_by=None, claimed_at=None, closed_at=None,
                revoked_at=None)


async def revoke(code: str) -> bool:
    """The citizen takes it back. Returns whether anything was revoked.

    Deliberately usable with nothing but the code: the person revoking may be
    on a borrowed phone, may not be the one who created it (a daughter helping
    her mother), and must never be asked to authenticate to withdraw consent
    they gave. Holding the code is the same evidence that granting it was.
    """
    from src.database import get_connection, revoke_case

    normalised = normalise(code)
    if not normalised:
        return False
    db = await get_connection()
    try:
        changed = await revoke_case(db, normalised, _now())
    finally:
        await db.close()
    if changed:
        logger.info("Case revoked by citizen")
    return bool(changed)


# ---------------------------------------------------------------------------
# The operator's side
# ---------------------------------------------------------------------------

async def claim(code: str, operator_id: str, organisation_id: str) -> Case:
    """Bind a case to one operator, once. Raises `DelegationError` otherwise.

    The binding is a conditional UPDATE — `WHERE claimed_by IS NULL` — and its
    row count is what makes "once" true. Reading the row, deciding it is free
    and then writing would let two operators at two counters both take the same
    case, which is the bug that matters here: two people filing the same
    application is a rejected application.
    """
    from src.database import claim_case, get_case, get_connection

    normalised = normalise(code)
    if not normalised:
        raise DelegationError(Refusal.UNKNOWN)

    db = await get_connection()
    try:
        row = await get_case(db, normalised)
        if row is None:
            raise DelegationError(Refusal.UNKNOWN)

        case = _to_case(row)
        if case.revoked_at:
            raise DelegationError(Refusal.REVOKED)
        if case.closed_at:
            raise DelegationError(Refusal.CLOSED)
        if case.claimed_by:
            # Re-presenting your own code is not an error; it is an operator
            # coming back to a case they already hold.
            if case.claimed_by == operator_id:
                return case
            raise DelegationError(Refusal.ALREADY_CLAIMED)
        if case.created_at < _claim_cutoff():
            raise DelegationError(Refusal.EXPIRED)

        claimed = await claim_case(db, normalised, operator_id,
                                   organisation_id, _now())
        if not claimed:
            # Somebody else took it between the read and the write. This is
            # exactly the race the conditional UPDATE exists to lose safely.
            raise DelegationError(Refusal.ALREADY_CLAIMED)
        row = await get_case(db, normalised)
    finally:
        await db.close()

    logger.info("Case %s claimed by operator %s", row[0], operator_id)
    return _to_case(row)


async def close(case_id: str, operator_id: str) -> bool:
    """The case is filed. Consent ends with it.

    `PRD-v3.md` §6.3 has the case close when filed, and that is a privacy
    property rather than housekeeping: an operator who finished the job three
    months ago should not still be able to read a household's income.
    """
    from src.database import close_case, get_connection

    db = await get_connection()
    try:
        changed = await close_case(db, case_id, operator_id, _now())
    finally:
        await db.close()
    if changed:
        logger.info("Case %s closed by %s", case_id, operator_id)
    return bool(changed)


async def caseload(operator_id: str, include_closed: bool = False) -> list[Case]:
    """Every case this operator holds. Theirs only — never the organisation's,
    unless and until there is a reason a colleague should see it."""
    from src.database import get_connection, operator_cases

    db = await get_connection()
    try:
        rows = await operator_cases(db, operator_id, include_closed)
    finally:
        await db.close()
    return [_to_case(r) for r in rows]


def _to_case(row) -> Case:
    """Positional, like every other read in this codebase — see dialect.py."""
    (case_id, code, context_json, scheme_slug, language, _citizen_ref,
     _scope, created_at, claimed_by, _claimed_org, claimed_at, closed_at,
     revoked_at) = row
    try:
        context = json.loads(context_json or "{}")
    except ValueError:
        context = {}
    return Case(case_id=case_id, code=code, context=context,
                scheme_slug=scheme_slug, language=language or "en",
                created_at=created_at, claimed_by=claimed_by,
                claimed_at=claimed_at, closed_at=closed_at,
                revoked_at=revoked_at)
