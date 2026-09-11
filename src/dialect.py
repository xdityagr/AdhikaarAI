"""
One set of statements, two databases.

The state this product keeps is tiny — opt-outs, a list of numbers, what we
learned about each of them, message idempotency. Seventy-odd kilobytes. SQLite
is the right shape for that and is what runs in tests and on a laptop.

It is the wrong shape for one specific thing: **surviving a deploy on a free
host.** Render's free plan gives a container an ephemeral filesystem, so the
opt-out table that took a commit to make durable would be erased every time the
service restarts — which is the original bug wearing a hat.

So `DATABASE_URL` selects Postgres and its absence selects SQLite, and the code
in `database.py` does not change either way.

WHY AN ADAPTER AND NOT AN ORM

Adding SQLAlchemy would mean rewriting every statement in the file and taking on
a large dependency to move five small tables. The difference between the two
dialects, once the SQL is written in the subset both accept, is exactly two
things:

  1. the placeholder — `?` against `%s`
  2. the connection API — `aiosqlite.execute()` hands back a cursor, while
     psycopg wants a cursor first

Both are a few lines. Everything else — `ON CONFLICT`, `RETURNING`, `TEXT`,
`INTEGER` — is already common to both, deliberately: `database.py` is written in
the dialect they share rather than in SQLite's, so this file only has to
translate, never rewrite.

ONE GOTCHA, AND IT IS WINDOWS-ONLY

psycopg's async mode refuses to run on `ProactorEventLoop`, which is asyncio's
default on Windows. Production is unaffected — Render is Linux — but a developer
who sets `DATABASE_URL` on a Windows machine gets an `InterfaceError` at connect
time rather than anything about databases. Run with a selector loop:

    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(
        selectors.SelectSelector()))

or simply leave `DATABASE_URL` unset locally, which is the intended default and
uses SQLite.

WHAT IS DELIBERATELY NOT HANDLED

`PRAGMA` is SQLite-only and is skipped on Postgres rather than emulated. The
pragmas exist to make SQLite behave the way Postgres already does — WAL so
readers do not block writers, a busy timeout so concurrent writers queue,
foreign keys on. Postgres needs no persuading.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)


def database_url() -> Optional[str]:
    """The Postgres URL, or None to stay on SQLite.

    Read from the environment rather than Settings so that it is available
    before configuration is loaded and so a deployment can switch databases
    without a code change — which is the whole point of naming it DATABASE_URL
    rather than something of our own.
    """
    url = (os.environ.get("DATABASE_URL") or "").strip()
    return url or None


def is_postgres() -> bool:
    return database_url() is not None


#: `?` outside quotes. The statements in database.py contain no string literals
#: with question marks in them, and this pattern is deliberately not a SQL
#: parser — if one ever appears, the right fix is to remove it, not to grow a
#: parser here.
_PLACEHOLDER = re.compile(r"\?")


def translate(sql: str) -> str:
    """SQLite's placeholder into psycopg's. Nothing else needs changing."""
    return _PLACEHOLDER.sub("%s", sql)


class Cursor:
    """The two rows-fetching methods `database.py` actually uses."""

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    async def fetchone(self):
        return await self._cursor.fetchone()

    async def fetchall(self):
        return await self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount or 0


class Connection:
    """An aiosqlite-shaped connection over psycopg.

    Only the surface `database.py` uses: `execute`, `commit`, `close`. Keeping
    it that small is what stops this becoming a database abstraction layer, and
    a database abstraction layer is a much larger thing to own than two
    dialects of five tables.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def execute(self, sql: str, params: Sequence = ()) -> Cursor:
        cursor = self._connection.cursor()
        await cursor.execute(translate(sql), tuple(params))
        return Cursor(cursor)

    async def executemany(self, sql: str, rows: Sequence[Sequence]) -> None:
        cursor = self._connection.cursor()
        await cursor.executemany(translate(sql), [tuple(r) for r in rows])

    async def commit(self) -> None:
        await self._connection.commit()

    async def close(self) -> None:
        await self._connection.close()


async def connect() -> Connection:
    """Open a Postgres connection shaped like an aiosqlite one.

    `row_factory=tuple_row` on purpose: SQLite here uses `aiosqlite.Row`, which
    indexes by position AND by name, and every read in `database.py` indexes by
    position. Returning dicts would work until the first `row[0]`.
    """
    import psycopg
    from psycopg.rows import tuple_row

    url = database_url()
    if not url:
        raise RuntimeError("connect() called with no DATABASE_URL")

    connection = await psycopg.AsyncConnection.connect(
        url, row_factory=tuple_row, autocommit=False)
    return Connection(connection)
