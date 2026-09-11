"""
The operator panel's HTTP surface, and the only guarded routes in this API.

Everything under `/api/operator` and `/api/partner` requires a live session.
That is enforced by one dependency — `current_operator` — rather than by a check
at the top of each handler, because a check you have to remember to write is a
check somebody will forget on the route added in a hurry the night before a
demo. `tests/test_operator_auth.py` walks the router and asserts that every
route in this file depends on it, so forgetting is a build failure.

WHAT THE COOKIE IS

`httponly` so a script on the page cannot read it. `samesite=lax` so it does not
ride on a cross-site POST. `secure` in production and not in local development,
because a `secure` cookie over plain http:// is simply never stored and the
login appears to succeed and then silently does nothing.

WHAT THE ERRORS SAY

"Email or password is incorrect", for a wrong password AND for an address with
no account. Saying which one was wrong turns the login form into a tool for
finding out which NGO workers have accounts here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints

from src import auth, delegation
from src.config import get_settings
from src.database import (
    close_all_sessions, close_session, create_operator, create_organisation,
    find_operator_by_email, get_case_by_id, get_connection, open_session,
    record_login_failure, record_login_success, session_operator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operator"])

#: The cookie's name. Prefixed like the rest of this product's cookies.
SESSION_COOKIE = "yojnasetu_operator"

#: The address is a LOGIN IDENTIFIER and nothing else. This system sends no
#: email — which is also why there is no password reset — so it is checked for
#: the shape of an address rather than validated to RFC 5322, and pydantic's
#: EmailStr is not pulled in, with its email-validator dependency, for a field
#: nothing is ever delivered to.
Email = Annotated[str, StringConstraints(
    strip_whitespace=True, to_lower=True, min_length=3, max_length=254,
    pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


def _production() -> bool:
    """Whether to mark the cookie `secure`.

    A `secure` cookie is dropped silently over http://, so getting this wrong in
    development makes login look broken in a way that leaves no trace anywhere.
    """
    settings = get_settings()
    return bool(getattr(settings, "public_base_url", "").startswith("https://"))


async def current_operator(
    token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> auth.Operator:
    """Who is making this request, or 401.

    The session id is NOT trusted the way `chat.get_session` trusts one. It is
    looked up, it must exist, it must not have expired, and the operator behind
    it must still be active — a revoked account has to stop working on the next
    request, not when its session happens to lapse.
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    db = await get_connection()
    try:
        row = await session_operator(db, auth.token_fingerprint(token))
        if row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

        operator_id, organisation_id, name, role, email, expires_at, active = row
        if auth.is_expired(expires_at):
            # Tidy it away rather than leaving a dead row to be swept later.
            await close_session(db, auth.token_fingerprint(token))
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        if not active:
            await close_all_sessions(db, operator_id)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    finally:
        await db.close()

    return auth.Operator(operator_id=operator_id,
                         organisation_id=organisation_id,
                         name=name, role=role, email=email)


def requires(*roles: str):
    """A dependency that also checks the role. `admin` passes everything."""
    async def check(operator: auth.Operator = Depends(current_operator)) -> auth.Operator:
        if not operator.may(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Your role does not allow this")
        return operator
    return check


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=512)


class OperatorOut(BaseModel):
    operator_id: str
    organisation_id: str
    name: str
    role: str
    email: str


@router.post("/operator/login", response_model=OperatorOut)
async def login(request: LoginRequest, response: Response) -> OperatorOut:
    """Exchange an email and password for a session cookie.

    Deliberately uniform: a wrong password and an unknown address take the same
    path, return the same message, and cost the same time — the dummy hash in
    `auth` exists so that "no such operator" does not return in a millisecond
    while a real account takes fifty.
    """
    db = await get_connection()
    try:
        row = await find_operator_by_email(db, request.email)

        if row is None:
            auth.verify_password(request.password, auth._DUMMY_HASH)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Email or password is incorrect")

        (operator_id, organisation_id, email, name, password_hash,
         role, active, failures, last_failure) = row

        locked = auth.locked_until(failures, last_failure)
        if locked:
            # Spend no time on the password at all. Also the one error that
            # tells the truth, because a person locked out by their own typing
            # needs to know to wait rather than to keep trying.
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many attempts. Try again shortly.")

        if not auth.verify_password(request.password, password_hash):
            await record_login_failure(db, operator_id)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Email or password is incorrect")

        if not active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

        token = auth.new_session_token()
        await open_session(db, auth.token_fingerprint(token), operator_id,
                           auth.session_expiry())
        await record_login_success(db, operator_id)
    finally:
        await db.close()

    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=auth.SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=_production(),
        path="/",
    )
    return OperatorOut(operator_id=operator_id, organisation_id=organisation_id,
                       name=name, role=role, email=email)


@router.post("/operator/logout")
async def logout(
    response: Response,
    token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    """Ends the session server-side, not only in the browser.

    Clearing the cookie alone would leave a working token in the database for
    anybody who had copied it — which is the whole reason sessions are held
    server-side rather than signed into the cookie itself.
    """
    if token:
        db = await get_connection()
        try:
            await close_session(db, auth.token_fingerprint(token))
        finally:
            await db.close()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/operator/me", response_model=OperatorOut)
async def me(operator: auth.Operator = Depends(current_operator)) -> OperatorOut:
    """Who am I — the call the panel makes on load to decide whether to show
    itself or the login form."""
    return OperatorOut(**operator.__dict__)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

class NewOperator(BaseModel):
    email: Email
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=512)
    role: str = "operator"
    organisation_id: Optional[str] = None


@router.post("/operator/accounts", response_model=OperatorOut,
             status_code=status.HTTP_201_CREATED)
async def add_operator(
    request: NewOperator,
    admin: auth.Operator = Depends(requires("admin")),
) -> OperatorOut:
    """Admins create accounts. There is no self-signup, by design.

    An operator account is permission to read other people's welfare
    applications; it is granted by somebody who knows who is being granted it,
    not by whoever can receive an email.

    Twelve characters minimum and no composition rules — length is what
    actually resists guessing, and "must contain a symbol" reliably produces
    Password1!.
    """
    if request.role not in auth.ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Role must be one of {', '.join(auth.ROLES)}")

    # An admin creates accounts in their OWN organisation unless they name
    # another. Defaulting to their own is what stops a slip creating an account
    # somewhere it does not belong.
    organisation_id = request.organisation_id or admin.organisation_id
    operator_id = uuid.uuid4().hex

    db = await get_connection()
    try:
        if await find_operator_by_email(db, request.email):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "An account with that email already exists")
        await create_operator(db, operator_id, organisation_id, request.email,
                              request.name, auth.hash_password(request.password),
                              request.role)
    finally:
        await db.close()

    logger.info("Operator %s created by %s", operator_id, admin.operator_id)
    return OperatorOut(operator_id=operator_id, organisation_id=organisation_id,
                       name=request.name, role=request.role,
                       email=request.email.lower())


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)


@router.post("/operator/password")
async def change_password(
    request: PasswordChange,
    operator: auth.Operator = Depends(current_operator),
) -> dict:
    """Changing a password ends every session it opened, including this one.

    If the reason for the change is that somebody else knows the old password,
    leaving their session alive defeats the point of changing it.
    """
    db = await get_connection()
    try:
        row = await find_operator_by_email(db, operator.email)
        if row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
        if not auth.verify_password(request.current_password, row[4]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Current password is incorrect")

        await db.execute(
            "UPDATE operators SET password_hash = ? WHERE operator_id = ?",
            (auth.hash_password(request.new_password), operator.operator_id),
        )
        await db.commit()
        await close_all_sessions(db, operator.operator_id)
    finally:
        await db.close()
    return {"ok": True, "signed_out": True}


class NewOrganisation(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(CSC|NGO|SCA|BANK)$")
    state: Optional[str] = None
    district: Optional[str] = None


@router.post("/operator/organisations", status_code=status.HTTP_201_CREATED)
async def add_organisation(
    request: NewOrganisation,
    admin: auth.Operator = Depends(requires("admin")),
) -> dict:
    organisation_id = uuid.uuid4().hex
    db = await get_connection()
    try:
        await create_organisation(db, organisation_id, request.name,
                                  request.kind, request.state, request.district)
    finally:
        await db.close()
    logger.info("Organisation %s created by %s", organisation_id,
                admin.operator_id)
    return {"organisation_id": organisation_id, "name": request.name}


@router.get("/operator/health")
async def operator_health(
    operator: auth.Operator = Depends(current_operator),
) -> dict:
    """Cheap authenticated ping, so the panel can tell "signed out" from "the
    engine is down" without interpreting a 401 from a data route."""
    return {"ok": True, "at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Cases — the citizen's delegation, from the operator's side
# ---------------------------------------------------------------------------

class ClaimRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class CaseOut(BaseModel):
    case_id: str
    code: str
    scheme_slug: Optional[str]
    language: str
    created_at: str
    claimed_at: Optional[str]
    closed_at: Optional[str]
    #: What the citizen chose to share. Returned only to the operator holding
    #: the case — never in a list, and never to a colleague.
    context: Optional[dict] = None


def _case_out(case: delegation.Case, with_context: bool = False) -> CaseOut:
    return CaseOut(
        case_id=case.case_id, code=case.code, scheme_slug=case.scheme_slug,
        language=case.language, created_at=case.created_at,
        claimed_at=case.claimed_at, closed_at=case.closed_at,
        context=case.context if with_context else None,
    )


#: Why a code was refused, in words an operator can act on. The refusal itself
#: is an enum so this mapping is total; a new refusal without a sentence here
#: is a KeyError at development time rather than a blank message at a counter.
_REFUSAL_TEXT = {
    delegation.Refusal.UNKNOWN:
        "No case with that code. Check the letters and try again.",
    delegation.Refusal.EXPIRED:
        "That code has expired. Ask them to create a new one.",
    delegation.Refusal.ALREADY_CLAIMED:
        "Another operator is already helping with this case.",
    delegation.Refusal.REVOKED:
        "The citizen has withdrawn this case.",
    delegation.Refusal.CLOSED:
        "This case has already been filed.",
}


@router.post("/operator/cases/claim", response_model=CaseOut)
async def claim_case_route(
    request: ClaimRequest,
    operator: auth.Operator = Depends(current_operator),
) -> CaseOut:
    """Take a case the citizen offered, by its code.

    An operator cannot create a case — there is no route that does, and that
    absence is the design. Everything the panel knows about a person is here
    because the person handed it over.

    Failure is loud, unlike the web-to-WhatsApp handoff it shares an alphabet
    with: "already claimed", "revoked" and "mistyped" lead to three different
    next actions for somebody with a person in front of them.
    """
    try:
        case = await delegation.claim(request.code, operator.operator_id,
                                      operator.organisation_id)
    except delegation.DelegationError as refused:
        status_code = (status.HTTP_409_CONFLICT
                       if refused.refusal in (delegation.Refusal.ALREADY_CLAIMED,
                                              delegation.Refusal.CLOSED)
                       else status.HTTP_404_NOT_FOUND)
        raise HTTPException(status_code, _REFUSAL_TEXT[refused.refusal])
    return _case_out(case, with_context=True)


@router.get("/operator/cases", response_model=list[CaseOut])
async def list_cases(
    include_closed: bool = False,
    operator: auth.Operator = Depends(current_operator),
) -> list[CaseOut]:
    """This operator's caseload, without the citizens' answers.

    The list is for choosing which case to open. Returning everyone's income
    and community in it would put a screenful of households in front of anybody
    who glances at a shared counter monitor.
    """
    cases = await delegation.caseload(operator.operator_id, include_closed)
    return [_case_out(c) for c in cases]


@router.get("/operator/cases/{case_id}", response_model=CaseOut)
async def read_case(
    case_id: str,
    operator: auth.Operator = Depends(current_operator),
) -> CaseOut:
    """One case in full, and only if this operator holds it.

    Checked against `claimed_by` rather than against the organisation: consent
    was given to a person at a counter, not to their employer.
    """
    db = await get_connection()
    try:
        row = await get_case_by_id(db, case_id)
    finally:
        await db.close()

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such case")
    case = delegation._to_case(row)
    # 404 rather than 403 for a case somebody else holds: a 403 would confirm
    # the case exists to anybody who can guess an id.
    if case.claimed_by != operator.operator_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such case")
    if case.revoked_at:
        raise HTTPException(status.HTTP_410_GONE,
                            "The citizen has withdrawn this case.")
    return _case_out(case, with_context=True)


@router.post("/operator/cases/{case_id}/close", response_model=CaseOut)
async def close_case_route(
    case_id: str,
    operator: auth.Operator = Depends(current_operator),
) -> CaseOut:
    """Filed. The consent ends with the case — an operator who finished the job
    three months ago should not still be able to read a household's income."""
    closed = await delegation.close(case_id, operator.operator_id)
    if not closed:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No open case of yours with that id")
    db = await get_connection()
    try:
        row = await get_case_by_id(db, case_id)
    finally:
        await db.close()
    return _case_out(delegation._to_case(row))
