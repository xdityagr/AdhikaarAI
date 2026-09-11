"""
The SQL is written in the dialect both databases accept.

`src/dialect.py` translates exactly one thing — the placeholder — and that is
only true for as long as `database.py` stays inside the shared subset. The
moment somebody writes `INSERT OR IGNORE` again, SQLite keeps working, every
test keeps passing, and production breaks on a syntax error nobody can reproduce
locally.

So these tests read the statements and check the dialect, rather than waiting
for a Postgres to be available. The real Postgres round-trip was run by hand
against a local cluster: init_database, users with language retention, consent,
the handoff's DELETE ... RETURNING single-use claim, user_context
save/load/forget, and ON CONFLICT DO NOTHING idempotency.

They read the parse tree rather than the file text, deliberately. `database.py`
explains at two points why it does NOT use `INSERT OR IGNORE` and why it does
NOT use `dict(row)`, and a grep over the raw source fails on the prose that
documents the rule — which teaches whoever hits it that the test is noise.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src import dialect

SOURCE = (Path(__file__).resolve().parents[1] / "src" / "database.py").read_text(
    encoding="utf-8")
TREE = ast.parse(SOURCE)


def _docstrings() -> set[int]:
    """Node ids of every docstring, so prose is not mistaken for a statement."""
    out = set()
    for node in ast.walk(TREE):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _sql() -> list[str]:
    """Every string literal that is not a docstring — i.e. the statements."""
    skip = _docstrings()
    return [n.value for n in ast.walk(TREE)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in skip]


STATEMENTS = _sql()

#: child -> parent, so a node can be asked which branch it sits on.
_PARENT = {id(c): p for p in ast.walk(TREE) for c in ast.iter_child_nodes(p)}
_NODES = {id(n): n for n in ast.walk(TREE)}


def _mentions_postgres(test: ast.AST) -> bool:
    return any((isinstance(n, ast.Name) and n.id == "is_postgres")
               or (isinstance(n, ast.Attribute) and n.attr == "is_postgres")
               for n in ast.walk(test))


def _on_the_sqlite_branch(node: ast.AST) -> bool:
    """True if `node` can only run when the dialect is SQLite.

    Walks up to the module, asking at each `If` whether this node is on the
    branch not taken under Postgres — the `else` of `if is_postgres()`, or the
    body of `if not is_postgres()`. `_set_pragmas` counts because only the
    SQLite half of `get_connection` calls it.
    """
    child = node
    while (parent := _NODES.get(id(_PARENT.get(id(child))))) is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if parent.name == "_set_pragmas":
                return True
        if isinstance(parent, ast.If) and _mentions_postgres(parent.test):
            negated = isinstance(parent.test, ast.UnaryOp) and isinstance(
                parent.test.op, ast.Not)
            on_else = any(child is s or child in ast.walk(s)
                          for s in parent.orelse)
            if on_else is not negated:
                return True
        child = parent
    return False


class TestPlaceholderTranslation:
    def test_a_single_placeholder(self):
        assert dialect.translate("SELECT 1 WHERE a = ?") == "SELECT 1 WHERE a = %s"

    def test_several(self):
        assert dialect.translate("VALUES (?, ?, ?)") == "VALUES (%s, %s, %s)"

    def test_a_statement_with_none_is_untouched(self):
        sql = "SELECT user_id FROM consent WHERE opted_out = 1"
        assert dialect.translate(sql) == sql

    def test_on_conflict_survives_translation(self):
        """The clause that makes the statement portable in the first place."""
        sql = ("INSERT INTO t (a, b) VALUES (?, ?) "
               "ON CONFLICT (a) DO UPDATE SET b=excluded.b")
        out = dialect.translate(sql)
        assert "ON CONFLICT (a) DO UPDATE SET b=excluded.b" in out
        assert "%s" in out and "?" not in out


class TestTheSqlStaysPortable:
    """Read the statements in database.py and refuse SQLite-only spellings."""

    @pytest.mark.parametrize("forbidden", [
        "INSERT OR IGNORE",
        "INSERT OR REPLACE",
        "INSERT OR ROLLBACK",
        "AUTOINCREMENT",
    ])
    def test_no_sqlite_only_syntax(self, forbidden):
        guilty = [s for s in STATEMENTS if forbidden in s.upper()]
        assert not guilty, (
            f"{forbidden} is valid SQLite and invalid Postgres. Use "
            f"ON CONFLICT, which both accept. Found in: {guilty[:1]}"
        )

    def test_pragmas_are_guarded(self):
        """PRAGMA is SQLite-only and must never reach Postgres.

        Each one must sit on the SQLite side of an `is_postgres()` branch, or
        inside `_set_pragmas`, which only the SQLite connection path calls.

        "Somewhere in a function that also mentions the dialect" is not enough:
        `_ensure_columns` branches on the dialect and then does more work
        afterwards, so a PRAGMA added below the branch would run on both.
        """
        skip = _docstrings()
        for node in ast.walk(TREE):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "PRAGMA" in node.value.upper()
                    and id(node) not in skip):
                continue
            assert _on_the_sqlite_branch(node), (
                f"database.py:{node.lineno} runs a PRAGMA that Postgres will "
                f"also reach. Put it on the else-branch of is_postgres(), or "
                f"in _set_pragmas().")

    def test_rows_are_read_by_position(self):
        """SQLite returns aiosqlite.Row, which indexes by name and position;
        psycopg returns tuples. One `dict(row)` is all it takes to break."""
        for node in ast.walk(TREE):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "dict"
                    and node.args):
                pytest.fail(
                    f"database.py:{node.lineno} builds a dict from a row. That "
                    f"needs a name-indexable row, which psycopg does not give.")


class TestSelection:
    def test_no_url_means_sqlite(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert not dialect.is_postgres()
        assert dialect.database_url() is None

    def test_a_url_means_postgres(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/db")
        assert dialect.is_postgres()

    def test_an_empty_url_means_sqlite(self, monkeypatch):
        """An env var set to "" is how a platform spells "unset", and treating
        it as a URL would fail at connect rather than fall back."""
        monkeypatch.setenv("DATABASE_URL", "   ")
        assert not dialect.is_postgres()

    async def test_connect_without_a_url_is_a_clear_error(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            await dialect.connect()
