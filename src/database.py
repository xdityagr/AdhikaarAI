"""
Database module — async SQLite with WAL mode.

Handles:
- Connection factory with correct pragmas (WAL, busy_timeout, etc.)
- DDL for all custom tables (NOT conversation_state — that's LangGraph's job)
- Idempotency queries (processed_messages)
- User management queries

Architecture.md Non-negotiable #2: conversation state is handled by
LangGraph's AsyncSqliteSaver checkpointer, not by a custom table here.
"""

from __future__ import annotations

import aiosqlite
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src import dialect
from src.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL — every table we manage (LangGraph manages its own checkpointer tables)
# ---------------------------------------------------------------------------

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        preferred_language TEXT DEFAULT 'en',
        created_at TEXT NOT NULL,
        last_active_at TEXT NOT NULL
    )
    """,
    # Who asked to be left alone.
    #
    # This was a module-level set() in whatsapp_consent.py, which meant a
    # restart forgot it — and render.yaml names that as the one data loss here
    # that is not merely inconvenient. Messaging someone who sent STOP is not a
    # degraded experience, it is the thing the file exists to prevent.
    #
    # A row per number rather than a set of the opted-out, because opting back
    # IN is also a decision worth keeping: a deleted row and a never-seen number
    # are indistinguishable, and the alert layer will want to tell them apart.
    """
    CREATE TABLE IF NOT EXISTS consent (
        user_id TEXT PRIMARY KEY,
        opted_out INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """,
    # A conversation parked on the website, waiting to be picked up on WhatsApp.
    #
    # `created_at` is wall-clock rather than the monotonic clock the in-memory
    # version used. Monotonic is the right choice for a process — immune to the
    # clock being adjusted — and the wrong one for a row, because it resets to
    # zero on restart and every stored handoff would read as brand new.
    """
    CREATE TABLE IF NOT EXISTS handoff (
        code TEXT PRIMARY KEY,
        context TEXT NOT NULL,
        history TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    # What we have learned about a person, so they do not have to say it twice
    # on a different channel.
    #
    # Keyed on the phone number because that is the only identifier that spans
    # WhatsApp and a phone call, and the only one somebody gives us by their own
    # action rather than by being tracked. The website contributes through a
    # handoff code, which is explicit and consented; nothing here is collected
    # from a browser that never crossed over.
    #
    # Deleted outright on STOP. "Leave me alone" cannot mean "we will stop
    # writing but keep what we have."
    """
    CREATE TABLE IF NOT EXISTS user_context (
        user_id TEXT PRIMARY KEY,
        context TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS processed_messages (
        message_id TEXT PRIMARY KEY,
        processed_at TEXT NOT NULL
    )
    """,
    # ---- the operator panel ------------------------------------------------
    #
    # The only accounts in this system. Citizens have none and are never asked
    # for one; these are the CSC operators, NGO workers and SCA staff who file
    # on somebody's behalf, and they exist so that a view of other people's
    # welfare applications is not a public one.
    """
    CREATE TABLE IF NOT EXISTS organisations (
        organisation_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        -- CSC | NGO | SCA | BANK. Not the prudential discriminator on
        -- channel_partners; this is simply who they are.
        kind TEXT NOT NULL,
        state TEXT,
        district TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS operators (
        operator_id TEXT PRIMARY KEY,
        organisation_id TEXT NOT NULL,
        -- Lower-cased at write time so a login cannot be defeated by capitals,
        -- and UNIQUE so two accounts cannot share one address.
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        -- Set to 0 to revoke access without deleting the audit trail of what
        -- this person did. Deleting an operator would orphan their caseload.
        active INTEGER NOT NULL DEFAULT 1,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        last_failure_at TEXT,
        last_login_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # A citizen's case, handed to an operator by the citizen.
    #
    # The only route by which anything about a person reaches a server and
    # stays there. No operator can create a row here; they redeem a code the
    # citizen gave them, and the citizen can revoke it with nothing but that
    # same code — asking somebody to authenticate in order to WITHDRAW consent
    # would be a worse bargain than the one they agreed to.
    #
    # `scope` records what was agreed rather than assuming it, so widening what
    # the panel does later cannot silently re-interpret consent already given.
    """
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        -- What the citizen chose to share. Their answers, not their documents.
        context TEXT NOT NULL,
        scheme_slug TEXT,
        -- An operator who speaks to them in the wrong language has undone most
        -- of the point of this product.
        language TEXT NOT NULL DEFAULT 'en',
        -- Their number, when they came through WhatsApp, so a revocation can
        -- be honoured from the channel they already use. Null on the website.
        citizen_ref TEXT,
        scope TEXT NOT NULL,
        created_at TEXT NOT NULL,
        -- NULL until an operator takes it. The conditional UPDATE against this
        -- column is what stops two counters filing the same application.
        claimed_by TEXT,
        claimed_org TEXT,
        claimed_at TEXT,
        closed_at TEXT,
        revoked_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS operator_sessions (
        -- The SHA-256 of the cookie's token, never the token. A leaked table
        -- must not be a set of live logins.
        token_hash TEXT PRIMARY KEY,
        operator_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    # Who has already been told about which scheme.
    #
    # Idempotency for the alert job, and the reason a corpus re-ingest that
    # bumps first_seen does not tell four thousand people about the same
    # scheme a second time. A row is written even in the runs where the
    # template send is batched, because "told" means the person was notified
    # about this scheme at all — not that a message was sent per scheme.
    """
    CREATE TABLE IF NOT EXISTS alerts_sent (
        user_id TEXT NOT NULL,
        scheme_slug TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        PRIMARY KEY (user_id, scheme_slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendation_cache (
        profile_fingerprint TEXT NOT NULL,
        language TEXT NOT NULL,
        scheme_id TEXT NOT NULL,
        explanation TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (profile_fingerprint, language)
    )
    """,
    # NOTE: there was a `schemes` table here. It was dead — nothing ever read it,
    # and eligibility has always read the scheme corpus in Python. Worse, its
    # columns (min_age, max_age, requires_student, target_category) were exactly
    # the unverified fields deliberately removed from config. Two sources of truth
    # for scheme numbers is the hazard this project is trying to solve, so the
    # table is gone. The corpus (corpus/v1/schemes.json) is the single source.
    #
    # channel_partners: two DIFFERENT type discriminators live here, deliberately.
    #   agency_type  — PRUDENTIAL discriminator ("SCA"/"RRB"/"OTHER"). Keys
    #                  PRUDENTIAL_NORMS. Which rule applies to this partner?
    #   partner_type — RATE/CAPABILITY discriminator, one of NSFDC's 8 published
    #                  categories. Determines the beneficiary's interest rate
    #                  (Udyam Nidhi is 13% via a cooperative bank, 15% via a small
    #                  finance bank) and which schemes the partner may process.
    # They are not interchangeable. Don't collapse them.
    """
    CREATE TABLE IF NOT EXISTS channel_partners (
        partner_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        agency_type TEXT NOT NULL,
        state TEXT,
        district TEXT,
        latitude REAL,
        longitude REAL,
        net_npa_percentage REAL DEFAULT 0.0,
        cumulative_utilization REAL DEFAULT 1.0,
        has_active_overdues INTEGER DEFAULT 0,
        partner_type TEXT,
        pincode TEXT,
        address TEXT,
        confidence TEXT DEFAULT 'MOCKED',
        source_url TEXT,
        fetched_at TEXT,
        corpus_version TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS partner_performance (
        scope TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        period TEXT NOT NULL,
        allocation REAL,
        disbursed REAL,
        cumulative_utilization REAL,
        beneficiaries INTEGER,
        confidence TEXT NOT NULL DEFAULT 'MOCKED',
        source_url TEXT,
        fetched_at TEXT,
        PRIMARY KEY (scope, scope_key, period)
    )
    """,
    # First indexes in this file. The router looks partners up by state/district
    # and by rough geography, and does it on the hot path.
    "CREATE INDEX IF NOT EXISTS idx_partners_state ON channel_partners(state)",
    "CREATE INDEX IF NOT EXISTS idx_partners_district ON channel_partners(district)",
    "CREATE INDEX IF NOT EXISTS idx_partners_geo ON channel_partners(latitude, longitude)",
    "CREATE INDEX IF NOT EXISTS idx_partners_type ON channel_partners(partner_type)",
]


# Additive column upgrades for databases created before a column existed.
# Kept in lockstep with DDL_STATEMENTS above: DDL is the desired end state,
# this is the upgrade path for an existing file. Edit both together.
ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "channel_partners": {
        "partner_type": "TEXT",
        "pincode": "TEXT",
        "address": "TEXT",
        "confidence": "TEXT DEFAULT 'MOCKED'",
        "source_url": "TEXT",
        "fetched_at": "TEXT",
        "corpus_version": "TEXT",
    },
}


async def _set_pragmas(db: aiosqlite.Connection) -> None:
    """Set SQLite pragmas for performance and correctness.

    - WAL mode: readers and writers don't block each other
    - busy_timeout 5000ms: concurrent writers queue instead of SQLITE_BUSY
    - synchronous NORMAL: safe with WAL, better write performance
    - foreign_keys ON: enforce referential integrity
    """
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA foreign_keys=ON")


async def get_connection():
    """A connection, to whichever database this deployment is using.

    `DATABASE_URL` selects Postgres; its absence selects SQLite. Nothing else in
    this file knows the difference, because `src/dialect.py` returns a
    connection with the same small surface either way.

    The reason both exist: SQLite is exactly the right shape for seventy
    kilobytes of state and is what tests and a laptop use, and it is the wrong
    shape for surviving a deploy on a free host, where the container filesystem
    is ephemeral and the opt-out table would be erased on every restart.
    """
    if dialect.is_postgres():
        return await dialect.connect()

    settings = get_settings()
    # Ensure the data directory exists
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await _set_pragmas(db)
    return db


async def _ensure_columns(
    db: aiosqlite.Connection,
    table: str,
    columns: dict[str, str],
) -> list[str]:
    """Add any missing columns to an existing table. Returns the columns added.

    This is NOT a migration system, and shouldn't grow into one. It is additive
    only: it cannot rename, drop, retype, add constraints, or backfill, and it
    keeps no version history. It exists because `CREATE TABLE IF NOT EXISTS` is
    a no-op on a table that already exists, so a developer with an older
    data/yojnasetu.db would otherwise hit "no such column" at runtime — during
    demo prep, most likely, which is the worst possible time.

    For anything this can't express, delete data/yojnasetu.db and let
    init_database() rebuild it.
    """
    if dialect.is_postgres():
        # `information_schema` is the standard spelling of the same question.
        cursor = await db.execute(
            "SELECT ordinal_position, column_name FROM information_schema.columns "
            "WHERE table_name = ?", (table,))
    else:
        cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    if not rows:
        # Table doesn't exist yet — DDL will create it with every column.
        return []

    existing = {row[1] for row in rows}
    added: list[str] = []
    for name, decl in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            added.append(name)
    return added


async def init_database() -> None:
    """Create all tables if they don't exist. Called once at app startup."""
    db = await get_connection()
    try:
        for ddl in DDL_STATEMENTS:
            await db.execute(ddl)
            # Postgres will not run another statement on a connection whose
            # transaction has failed, so each DDL is committed as it lands.
            # On SQLite this is a no-op beyond a flush.
            if dialect.is_postgres():
                await db.commit()

        for table, columns in ADDITIVE_COLUMNS.items():
            added = await _ensure_columns(db, table, columns)
            if added:
                logger.info("Added columns to %s: %s", table, ", ".join(added))

        await db.commit()
        where = "Postgres" if dialect.is_postgres() else get_settings().database_path
        logger.info("Database initialized successfully at %s", where)
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Idempotency — processed_messages
# ---------------------------------------------------------------------------

async def is_message_processed(db: aiosqlite.Connection, message_id: str) -> bool:
    """Check if a message has already been processed (idempotency guard)."""
    cursor = await db.execute(
        "SELECT 1 FROM processed_messages WHERE message_id = ?",
        (message_id,),
    )
    row = await cursor.fetchone()
    return row is not None


async def mark_message_processed(db: aiosqlite.Connection, message_id: str) -> None:
    """Record a message as processed. Idempotent.

    `ON CONFLICT DO NOTHING` rather than `INSERT OR IGNORE`: both say the same
    thing to SQLite, but only one of them is also valid Postgres. Every
    statement in this file is written in the dialect both accept, so moving to
    Postgres is a driver change and not a rewrite.
    """
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO processed_messages (message_id, processed_at) VALUES (?, ?) "
        "ON CONFLICT (message_id) DO NOTHING",
        (message_id, now),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# What we know about a person, across channels
# ---------------------------------------------------------------------------

async def load_context(db: aiosqlite.Connection, user_id: str) -> Optional[str]:
    cursor = await db.execute(
        "SELECT context FROM user_context WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else None


async def save_context(db: aiosqlite.Connection, user_id: str,
                       context: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO user_context (user_id, context, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             context=excluded.context, updated_at=excluded.updated_at""",
        (user_id, context, now),
    )
    await db.commit()


async def forget_context(db: aiosqlite.Connection, user_id: str) -> None:
    """Erase everything we learned. Called on STOP."""
    await db.execute("DELETE FROM user_context WHERE user_id = ?", (user_id,))
    await db.commit()


# ---------------------------------------------------------------------------
# Handoff — web to WhatsApp
# ---------------------------------------------------------------------------

async def put_handoff(db: aiosqlite.Connection, code: str, context: str,
                      history: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO handoff (code, context, history, created_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (code) DO UPDATE SET "
        "  context=excluded.context, history=excluded.history, "
        "  created_at=excluded.created_at",
        (code, context, history, now),
    )
    await db.commit()


async def take_handoff(db: aiosqlite.Connection, code: str) -> Optional[tuple]:
    """Redeem a code, once, atomically.

    DELETE ... RETURNING rather than SELECT-then-DELETE: two people racing the
    same code — the same link forwarded twice, or a message redelivered by Meta
    — must not both be handed the payload. One statement, one winner, and it
    ports to Postgres unchanged.
    """
    cursor = await db.execute(
        "DELETE FROM handoff WHERE code = ? RETURNING context, history, created_at",
        (code,),
    )
    row = await cursor.fetchone()
    await db.commit()
    return tuple(row) if row else None


async def sweep_handoffs(db: aiosqlite.Connection, older_than: str) -> int:
    """Drop handoffs past their TTL. Returns how many went."""
    cursor = await db.execute(
        "DELETE FROM handoff WHERE created_at < ?", (older_than,))
    await db.commit()
    return cursor.rowcount or 0


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

async def load_opted_out(db: aiosqlite.Connection) -> set[str]:
    """Every number that has asked to be left alone.

    Read once at startup into the in-memory set the hot path checks. The set is
    small — it is the people who said STOP — and `has_opted_out` is consulted on
    every inbound message and on every candidate of every alert run, so it must
    not be a query.
    """
    cursor = await db.execute("SELECT user_id FROM consent WHERE opted_out = 1")
    return {row[0] for row in await cursor.fetchall()}


async def set_consent(db: aiosqlite.Connection, user_id: str,
                      opted_out: bool) -> None:
    """Record a STOP or a START, durably, before we act on it."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO consent (user_id, opted_out, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             opted_out=excluded.opted_out, updated_at=excluded.updated_at""",
        (user_id, int(opted_out), now),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

async def touch_user(db: aiosqlite.Connection, user_id: str,
                     language: Optional[str] = None) -> None:
    """Record that we have heard from this number, and in which language.

    The `users` table has existed since the first commit with `get_or_create_user`
    as its only accessor and NO CALLERS, so it was created empty at every startup
    and stayed empty. That is fine while every conversation is inbound — and
    fatal the moment something wants to reach out, because there is no list of
    numbers to reach and no way to know what language to write in.

    `language` is only written when we actually know it: overwriting a person's
    remembered Hindi with a default of "en" because one message arrived as a
    photo would be worse than not updating at all.
    """
    now = datetime.now(timezone.utc).isoformat()
    if language:
        await db.execute(
            """INSERT INTO users (user_id, preferred_language, created_at, last_active_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 preferred_language=excluded.preferred_language,
                 last_active_at=excluded.last_active_at""",
            (user_id, language, now, now),
        )
    else:
        await db.execute(
            """INSERT INTO users (user_id, preferred_language, created_at, last_active_at)
               VALUES (?, 'en', ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET last_active_at=excluded.last_active_at""",
            (user_id, now, now),
        )
    await db.commit()


async def known_users(db: aiosqlite.Connection) -> list[tuple[str, str]]:
    """Every number we have heard from, with its language. For the alert layer."""
    cursor = await db.execute(
        "SELECT user_id, preferred_language FROM users ORDER BY last_active_at DESC")
    return [(row[0], row[1] or "en") for row in await cursor.fetchall()]


async def get_or_create_user(db: aiosqlite.Connection, user_id: str) -> dict:
    """Get existing user or create a new one. Returns user dict."""
    cursor = await db.execute(
        "SELECT user_id, preferred_language, created_at, last_active_at FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()

    now = datetime.now(timezone.utc).isoformat()

    if row is not None:
        # Update last_active_at
        await db.execute(
            "UPDATE users SET last_active_at = ? WHERE user_id = ?",
            (now, user_id),
        )
        await db.commit()
        # Built by position rather than `dict(row)`. SQLite hands back an
        # aiosqlite.Row, which indexes both ways; psycopg hands back a tuple.
        # Every other read in this file is already positional, and one
        # name-based access would be the only thing standing between here and
        # Postgres.
        return {
            "user_id": row[0],
            "preferred_language": row[1],
            "created_at": row[2],
            "last_active_at": row[3],
        }
    else:
        # Create new user
        await db.execute(
            "INSERT INTO users (user_id, preferred_language, created_at, last_active_at) VALUES (?, 'en', ?, ?)",
            (user_id, now, now),
        )
        await db.commit()
        return {
            "user_id": user_id,
            "preferred_language": "en",
            "created_at": now,
            "last_active_at": now,
        }


# ---------------------------------------------------------------------------
# The operator panel
#
# Positional reads throughout, like everything above, so this works unchanged
# on Postgres. `ON CONFLICT` rather than `INSERT OR REPLACE` for the same
# reason.
# ---------------------------------------------------------------------------

async def create_organisation(db, organisation_id: str, name: str, kind: str,
                              state: Optional[str] = None,
                              district: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO organisations
               (organisation_id, name, kind, state, district, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(organisation_id) DO UPDATE SET
             name=excluded.name, kind=excluded.kind,
             state=excluded.state, district=excluded.district""",
        (organisation_id, name, kind, state, district, now),
    )
    await db.commit()


async def create_operator(db, operator_id: str, organisation_id: str,
                          email: str, name: str, password_hash: str,
                          role: str) -> None:
    """One account. The email is lower-cased here rather than at every call
    site, so a login cannot be defeated by capitals."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO operators
               (operator_id, organisation_id, email, name, password_hash,
                role, active, failed_attempts, created_at)
           VALUES (?,?,?,?,?,?,1,0,?)""",
        (operator_id, organisation_id, email.strip().lower(), name,
         password_hash, role, now),
    )
    await db.commit()


async def find_operator_by_email(db, email: str) -> Optional[tuple]:
    """`(operator_id, organisation_id, email, name, password_hash, role,
    active, failed_attempts, last_failure_at)`, or None."""
    cursor = await db.execute(
        """SELECT operator_id, organisation_id, email, name, password_hash,
                  role, active, failed_attempts, last_failure_at
           FROM operators WHERE email = ?""",
        (email.strip().lower(),),
    )
    return await cursor.fetchone()


async def record_login_failure(db, operator_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """UPDATE operators
           SET failed_attempts = failed_attempts + 1, last_failure_at = ?
           WHERE operator_id = ?""",
        (now, operator_id),
    )
    await db.commit()


async def record_login_success(db, operator_id: str) -> None:
    """Clears the counter, so somebody who mistypes twice and then gets it
    right is not one mistake away from a lockout tomorrow."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """UPDATE operators
           SET failed_attempts = 0, last_failure_at = NULL, last_login_at = ?
           WHERE operator_id = ?""",
        (now, operator_id),
    )
    await db.commit()


async def open_session(db, token_hash: str, operator_id: str,
                       expires_at: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO operator_sessions
               (token_hash, operator_id, created_at, expires_at)
           VALUES (?,?,?,?)
           ON CONFLICT(token_hash) DO UPDATE SET expires_at=excluded.expires_at""",
        (token_hash, operator_id, now, expires_at),
    )
    await db.commit()


async def session_operator(db, token_hash: str) -> Optional[tuple]:
    """The operator behind a live session token, joined in one query.

    Returns `(operator_id, organisation_id, name, role, email, expires_at,
    active)`. Expiry is checked by the caller rather than in SQL, because
    comparing ISO strings in SQL works by luck and not by design.
    """
    cursor = await db.execute(
        """SELECT o.operator_id, o.organisation_id, o.name, o.role, o.email,
                  s.expires_at, o.active
           FROM operator_sessions s
           JOIN operators o ON o.operator_id = s.operator_id
           WHERE s.token_hash = ?""",
        (token_hash,),
    )
    return await cursor.fetchone()


async def close_session(db, token_hash: str) -> None:
    await db.execute("DELETE FROM operator_sessions WHERE token_hash = ?",
                     (token_hash,))
    await db.commit()


async def close_all_sessions(db, operator_id: str) -> None:
    """Every session this operator has, everywhere. What "revoke access" has
    to mean, and what a password change has to do."""
    await db.execute("DELETE FROM operator_sessions WHERE operator_id = ?",
                     (operator_id,))
    await db.commit()


async def sweep_sessions(db, now_iso: str) -> int:
    """Delete sessions that have expired. Returns how many went."""
    cursor = await db.execute(
        "DELETE FROM operator_sessions WHERE expires_at <= ?", (now_iso,))
    await db.commit()
    return cursor.rowcount or 0


# ---------------------------------------------------------------------------
# Cases — a citizen's delegation to an operator
#
# Every write here is conditional on the state it expects to find, and returns
# how many rows it changed. Read-then-write would let two operators at two
# counters both take one case, and two people filing the same application is a
# rejected application.
# ---------------------------------------------------------------------------

CASE_COLUMNS = ("case_id, code, context, scheme_slug, language, citizen_ref, "
                "scope, created_at, claimed_by, claimed_org, claimed_at, "
                "closed_at, revoked_at")


async def put_case(db, case_id: str, code: str, context: str,
                   scheme_slug: Optional[str], language: str,
                   citizen_ref: Optional[str], scope: str,
                   created_at: str) -> None:
    await db.execute(
        """INSERT INTO cases
               (case_id, code, context, scheme_slug, language, citizen_ref,
                scope, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id, code, context, scheme_slug, language, citizen_ref,
         scope, created_at),
    )
    await db.commit()


async def get_case(db, code: str) -> Optional[tuple]:
    cursor = await db.execute(
        f"SELECT {CASE_COLUMNS} FROM cases WHERE code = ?", (code,))
    return await cursor.fetchone()


async def get_case_by_id(db, case_id: str) -> Optional[tuple]:
    cursor = await db.execute(
        f"SELECT {CASE_COLUMNS} FROM cases WHERE case_id = ?", (case_id,))
    return await cursor.fetchone()


async def claim_case(db, code: str, operator_id: str, organisation_id: str,
                     when: str) -> int:
    """Bind a free case to one operator. Returns rows changed — 0 means
    somebody else got there first, which is the race this exists to lose
    safely."""
    cursor = await db.execute(
        """UPDATE cases
           SET claimed_by = ?, claimed_org = ?, claimed_at = ?
           WHERE code = ? AND claimed_by IS NULL
                 AND revoked_at IS NULL AND closed_at IS NULL""",
        (operator_id, organisation_id, when, code),
    )
    await db.commit()
    return cursor.rowcount or 0


async def revoke_case(db, code: str, when: str) -> int:
    """The citizen withdraws consent. Works whether or not it was claimed, and
    does not require knowing who holds it."""
    cursor = await db.execute(
        """UPDATE cases SET revoked_at = ?
           WHERE code = ? AND revoked_at IS NULL AND closed_at IS NULL""",
        (when, code),
    )
    await db.commit()
    return cursor.rowcount or 0


async def close_case(db, case_id: str, operator_id: str, when: str) -> int:
    """Filed. Only the operator holding it may close it, and a revoked case
    cannot be closed — it already ended, on the citizen's terms."""
    cursor = await db.execute(
        """UPDATE cases SET closed_at = ?
           WHERE case_id = ? AND claimed_by = ?
                 AND closed_at IS NULL AND revoked_at IS NULL""",
        (when, case_id, operator_id),
    )
    await db.commit()
    return cursor.rowcount or 0


async def operator_cases(db, operator_id: str,
                         include_closed: bool = False) -> list[tuple]:
    """This operator's caseload. A revoked case never appears again: the
    citizen ended it, and "closed" is not the same answer as "taken back"."""
    clause = "" if include_closed else " AND closed_at IS NULL"
    cursor = await db.execute(
        f"""SELECT {CASE_COLUMNS} FROM cases
            WHERE claimed_by = ? AND revoked_at IS NULL{clause}
            ORDER BY claimed_at DESC""",
        (operator_id,),
    )
    return list(await cursor.fetchall())


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

async def alert_already_sent(db, user_id: str, scheme_slug: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM alerts_sent WHERE user_id = ? AND scheme_slug = ?",
        (user_id, scheme_slug))
    return await cursor.fetchone() is not None


async def record_alert(db, user_id: str, scheme_slug: str, when: str) -> None:
    """ON CONFLICT DO NOTHING: telling somebody twice is the bug, so a second
    write is a no-op rather than an error that aborts the run."""
    await db.execute(
        """INSERT INTO alerts_sent (user_id, scheme_slug, sent_at)
           VALUES (?,?,?) ON CONFLICT(user_id, scheme_slug) DO NOTHING""",
        (user_id, scheme_slug, when))
    await db.commit()


async def forget_alerts(db, user_id: str) -> None:
    """STOP erases this too. Somebody who left and comes back is a new
    conversation, not one with a memory of what we already pushed at them."""
    await db.execute("DELETE FROM alerts_sent WHERE user_id = ?", (user_id,))
    await db.commit()
