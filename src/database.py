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
