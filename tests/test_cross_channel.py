"""
What we know about a person follows them between channels.

Everything the assistant learned lived in `_CONTEXT`, a dict in one process.
Someone who told WhatsApp their state on Monday was a stranger again on Tuesday,
and a person moving between the website, WhatsApp and (soon) a phone call was
three different strangers.

Keyed on the phone number, which is the only identifier that spans WhatsApp and
a call and the only one somebody hands over by their own action. The website
contributes through a handoff code, which is explicit and consented.

Two properties are load-bearing:

- **Durable facts persist; session junk does not.** A stale "reply 2 for the
  second one" restored days later is worse than no memory at all.
- **STOP erases it.** "Leave me alone" cannot mean "we will stop writing things
  down but keep what we have."
"""

from __future__ import annotations

import pytest

from src import whatsapp_brain as brain
from src import whatsapp_consent as consent
from src.database import init_database


@pytest.fixture(autouse=True)
async def _fresh():
    await init_database()
    brain._CONTEXT.clear()
    brain._HISTORY.clear()
    brain._LOADED.clear()
    consent._OPTED_OUT.clear()
    yield
    brain._CONTEXT.clear()
    brain._LOADED.clear()
    consent._OPTED_OUT.clear()


async def _restart() -> None:
    """What a redeploy does: lose the process, keep the database."""
    brain._CONTEXT.clear()
    brain._LOADED.clear()


class TestKnowledgeSurvives:
    async def test_what_we_learned_comes_back(self):
        user = "919000000201"
        brain._CONTEXT[user].update({"state": "Bihar", "caste": "sc"})
        await brain.save_context(user)

        await _restart()
        await brain.load_context(user)
        assert brain._CONTEXT[user]["state"] == "Bihar"
        assert brain._CONTEXT[user]["caste"] == "sc"

    async def test_language_comes_back(self):
        """The one that decides whether a message can be read at all."""
        user = "919000000202"
        brain.remember_detected_language(user, "ta")
        await brain.save_context(user)

        await _restart()
        await brain.load_context(user)
        assert brain.language_if_known(user) == "ta"

    async def test_loading_happens_once_per_process(self):
        user = "919000000203"
        brain._CONTEXT[user].update({"state": "Kerala"})
        await brain.save_context(user)
        await _restart()

        await brain.load_context(user)
        # A second call must not re-read and clobber anything learned since.
        brain._CONTEXT[user]["state"] = "Odisha"
        await brain.load_context(user)
        assert brain._CONTEXT[user]["state"] == "Odisha"

    async def test_this_session_beats_the_stored_copy(self):
        """Someone who says "actually I'm in Delhi now" must not be overruled
        by a row written last month."""
        user = "919000000204"
        brain._CONTEXT[user].update({"state": "Bihar"})
        await brain.save_context(user)
        await _restart()

        brain._CONTEXT[user]["state"] = "Delhi"       # said in this turn
        await brain.load_context(user)
        assert brain._CONTEXT[user]["state"] == "Delhi"


class TestSessionJunkIsNotRemembered:
    async def test_pending_map_is_not_stored(self):
        """A map URL expires in an hour. Restoring one later points at nothing."""
        user = "919000000205"
        brain._CONTEXT[user].update({"state": "Bihar", "pending_map": "/media/x.png"})
        await brain.save_context(user)

        await _restart()
        await brain.load_context(user)
        assert brain._CONTEXT[user]["state"] == "Bihar"
        assert "pending_map" not in brain._CONTEXT[user]

    async def test_last_options_are_not_stored(self):
        """Restoring "reply 2 for the second one" to somebody whose
        conversation moved on days ago is worse than no memory."""
        user = "919000000206"
        brain._CONTEXT[user].update({"state": "Bihar", "last_options": ["a", "b"]})
        await brain.save_context(user)

        await _restart()
        await brain.load_context(user)
        assert "last_options" not in brain._CONTEXT[user]


class TestStopErasesIt:
    async def test_forget_removes_the_stored_copy(self):
        user = "919000000207"
        brain._CONTEXT[user].update({"state": "Bihar", "caste": "sc"})
        await brain.save_context(user)

        await brain.forget(user)
        await _restart()
        await brain.load_context(user)
        assert not brain._CONTEXT.get(user), \
            "STOP left behind what we had been asked to forget"

    async def test_stop_through_the_real_turn_erases_it(self):
        """End to end, through `reply`, because that is the path a person
        actually takes."""
        user = "919000000208"
        brain._CONTEXT[user].update({"state": "Bihar"})
        await brain.save_context(user)

        answer = await brain.reply(user, "STOP")
        assert answer == consent.STOPPED

        await _restart()
        await brain.load_context(user)
        assert not brain._CONTEXT.get(user)
