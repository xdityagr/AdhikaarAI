"""
Accounts, for the people who file on a citizen's behalf.

This is the first authentication in the codebase, and it arrives for a specific
reason: the operator panel is a view of other people's welfare applications.
`MVP-PLAN.md` records the console as "Regressed — existed as a tab; the chat
rebuild dropped it", and rebuilding it without accounts would not be a console.
It would be a public database of poor households.

Everything the citizen product does is anonymous and stays that way. Nothing
here touches it: a person using the website or WhatsApp has no account, is never
asked for one, and their profile still lives only on their own phone.

WHAT IS PROTECTED AND HOW

  organisations     a CSC, an NGO, an SCA, a bank branch
  operators         a person at one of them, with a role
  operator_sessions a live login

Sessions are server-side and opaque. The cookie carries a random token; the
database stores only its SHA-256, so a leaked database does not hand anybody a
live session — the same reasoning that makes a password hash worth having.

`chat.get_session` is the pattern this deliberately does NOT follow. It accepts
any session id the client sends and creates it if it does not exist, which is
harmless for an anonymous chat and would be a catastrophe here.

WHY SCRYPT AND NOT ARGON2

Argon2id is the better algorithm and `argon2-cffi` is the usual way to get it.
scrypt is in the Python standard library, is on OWASP's list of acceptable
password KDFs, and needs no wheel, no compiler and no C library on the
deployment host. For a handful of operator accounts on a free container, the
dependency that cannot fail to install is worth more than the marginally
stronger KDF. The cost parameters are stated below and can be raised without a
migration, because each hash records the parameters it was made with.

WHAT THIS DOES NOT DO YET, STATED PLAINLY

  - no password reset (an admin sets one; there is no email in the system)
  - no rate limiting beyond the lockout counter below
  - no MFA

None of those are reasons to delay the panel, and all of them are reasons not to
claim more than is here.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

#: scrypt cost. n is the CPU/memory cost and dominates: 2**15 with r=8 is about
#: 32 MiB per hash. Logins are rare and a free container has 512 MiB, so this is
#: affordable; it is recorded in every hash so it can be raised later and old
#: hashes keep verifying.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32

#: How long a login lasts. Short enough that a shared terminal at a CSC does not
#: stay open all week; long enough not to interrupt a day's caseload.
SESSION_HOURS = 12

#: Failed attempts before an account stops accepting passwords, and for how
#: long. Crude, and it is the only brake on guessing that exists — so it counts
#: per account rather than per IP, because the account is what is being
#: attacked and an IP is trivially changed.
MAX_FAILURES = 8
LOCKOUT_MINUTES = 15

ROLES = ("operator", "partner", "admin")


class AuthError(Exception):
    """Login failed. Deliberately says no more than that — see `authenticate`."""


@dataclass(frozen=True)
class Operator:
    """Who is making this request."""
    operator_id: str
    organisation_id: str
    name: str
    role: str
    email: str

    def may(self, *roles: str) -> bool:
        return self.role in roles or self.role == "admin"


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """`scrypt$n$r$p$salt$key`, all base-16.

    The parameters travel with the hash so raising them later is a code change
    and not a migration: an old hash still says how it was made.
    """
    if not password:
        raise ValueError("empty password")
    salt = os.urandom(_SALT_BYTES)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                         n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                         dklen=_KEY_BYTES, maxmem=_SCRYPT_N * _SCRYPT_R * 256)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time, and False rather than an exception on a malformed hash."""
    try:
        scheme, n, r, p, salt_hex, key_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(key_hex)
    except (ValueError, AttributeError):
        # A truncated or hand-edited row must fail closed, not crash the login
        # route and turn a bad password into a 500.
        logger.warning("Unreadable password hash")
        return False

    candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                               n=n, r=r, p=p, dklen=len(expected),
                               maxmem=n * r * 256)
    return hmac.compare_digest(candidate, expected)


#: A hash of a password nobody has, used to spend the same time on a login for
#: an address that does not exist as one for an address that does. Without it,
#: "no such operator" returns in a millisecond and a real account takes fifty,
#: which is a user-enumeration oracle anybody can time from outside.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

def new_session_token() -> str:
    """What goes in the cookie. 32 bytes from `secrets`, URL-safe."""
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """What goes in the database.

    SHA-256 and not a password KDF: the token already has 256 bits of entropy
    from a CSPRNG, so there is nothing to brute-force and no reason to spend
    32 MiB verifying every request. The point of hashing it at all is that a
    leaked `operator_sessions` table must not be a set of live logins.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(hours: int = SESSION_HOURS) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def is_expired(expires_at: Optional[str]) -> bool:
    """Wall-clock, and an unreadable or missing expiry counts as expired."""
    if not expires_at:
        return True
    try:
        when = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= datetime.now(timezone.utc)


def locked_until(failures: int, last_failure: Optional[str]) -> Optional[str]:
    """When this account stops accepting passwords, if it does.

    Returns None when it is not locked. The counter is reset by a successful
    login, so a person who mistypes twice and then gets it right is not one
    mistake away from being locked out tomorrow.
    """
    if failures < MAX_FAILURES or not last_failure:
        return None
    try:
        when = datetime.fromisoformat(last_failure)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    until = when + timedelta(minutes=LOCKOUT_MINUTES)
    return until.isoformat() if until > datetime.now(timezone.utc) else None
