"""
Opt-out survives a restart.

This is the one data loss in the system that is not merely inconvenient —
`render.yaml` says so in as many words. Messaging a person who explicitly asked
to be left alone is not a degraded experience; it is the thing
`whatsapp_consent.py` exists to prevent, and until now a process restart undid
every STOP ever sent because the list was a module-level `set()`.

The tests below simulate the restart by clearing the in-memory cache and calling
`load()` again against the same database — which is exactly what a redeploy does.
"""

from __future__ import annotations

import pytest

from src import whatsapp_consent as consent
from src.database import get_connection, init_database, load_opted_out


@pytest.fixture(autouse=True)
async def _fresh_state():
    """A real database per test, and an empty cache to load into."""
    await init_database()
    consent._OPTED_OUT.clear()
    consent._loaded = False
    yield
    consent._OPTED_OUT.clear()
    consent._loaded = False


async def _restart() -> None:
    """What a redeploy does: lose the process, keep the database."""
    consent._OPTED_OUT.clear()
    consent._loaded = False
    await consent.load()


class TestOptOutIsDurable:
    async def test_stop_survives_a_restart(self):
        """The whole point of the table."""
        await consent.opt_out("919999900001")
        assert consent.has_opted_out("919999900001")

        await _restart()
        assert consent.has_opted_out("919999900001"), \
            "a restart forgot somebody who asked to be left alone"

    async def test_start_survives_a_restart_too(self):
        """Opting back in is also a decision, and losing it would re-silence
        someone who asked us to resume."""
        await consent.opt_out("919999900002")
        await consent.opt_in("919999900002")
        await _restart()
        assert not consent.has_opted_out("919999900002")

    async def test_a_number_never_seen_is_not_opted_out(self):
        await _restart()
        assert not consent.has_opted_out("919999900003")

    async def test_check_honours_stop_in_any_script(self):
        """STOP is written in every supported script precisely so nobody has to
        type English to make it stop."""
        for word in ("STOP", "बंद", "நிறுத்து", "বন্ধ"):
            number = f"9199999{abs(hash(word)) % 100000:05d}"
            assert await consent.check(number, word) == consent.STOPPED
            assert consent.has_opted_out(number)

    async def test_stop_twice_is_harmless(self):
        """STOP is honoured before the opted-out check, so sending it again
        acknowledges rather than ignores."""
        assert await consent.check("919999900004", "STOP") == consent.STOPPED
        assert await consent.check("919999900004", "STOP") == consent.STOPPED

    async def test_it_is_written_before_the_cache_is_updated(self):
        """If the process dies between the two, the durable record must already
        say opted-out. The failure has to lean towards messaging someone LESS."""
        await consent.opt_out("919999900005")
        db = await get_connection()
        try:
            stored = await load_opted_out(db)
        finally:
            await db.close()
        assert "919999900005" in stored


class TestOutboundSafety:
    async def test_is_loaded_is_false_before_loading(self):
        """An empty cache means "we have not looked", not "nobody opted out".

        Acting on the second reading would message every person who ever asked
        us to stop, so the alert job must refuse to run while this is False.
        """
        assert not consent.is_loaded()

    async def test_is_loaded_is_true_after_loading(self):
        await consent.load()
        assert consent.is_loaded()

    async def test_a_failed_load_does_not_claim_to_be_loaded(self, monkeypatch):
        """A database that will not open must leave `is_loaded()` False, or the
        safety check above becomes decorative."""
        async def explode():
            raise RuntimeError("no database")

        monkeypatch.setattr("src.database.get_connection", explode)
        await consent.load()
        assert not consent.is_loaded()

    async def test_a_failed_write_still_honours_stop_this_process(self, monkeypatch):
        """Durability is best-effort; honouring STOP is not.

        A disk problem must not mean we keep talking to someone who just told us
        to stop — it means we remember it for as long as we are running.
        """
        async def explode():
            raise RuntimeError("disk is busy")

        monkeypatch.setattr("src.database.get_connection", explode)
        await consent.opt_out("919999900006")
        assert consent.has_opted_out("919999900006")
