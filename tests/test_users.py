"""
There is a list of numbers, and it knows what language each one reads.

The `users` table existed from the first commit with `get_or_create_user` as its
only accessor and no callers at all, so it was created empty at every startup and
stayed empty. That is invisible while every conversation is inbound — and fatal
the moment anything wants to reach out, because there is no list of numbers to
reach and no way to know what language to write in.

Both halves matter. A change alert sent in English to somebody who has only ever
written in Tamil is a message that will not be read.
"""

from __future__ import annotations

import pytest

from src.database import get_connection, init_database, known_users, touch_user


@pytest.fixture(autouse=True)
async def _db():
    await init_database()
    yield


async def _users() -> dict[str, str]:
    db = await get_connection()
    try:
        return dict(await known_users(db))
    finally:
        await db.close()


async def _touch(user_id: str, language=None) -> None:
    db = await get_connection()
    try:
        await touch_user(db, user_id, language)
    finally:
        await db.close()


class TestTheListExists:
    async def test_a_number_we_have_heard_from_is_recorded(self):
        await _touch("919000000101", "hi")
        assert "919000000101" in await _users()

    async def test_the_language_is_recorded_with_it(self):
        await _touch("919000000102", "ta")
        assert (await _users())["919000000102"] == "ta"

    async def test_hearing_from_someone_twice_does_not_duplicate_them(self):
        await _touch("919000000103", "bn")
        await _touch("919000000103", "bn")
        users = await _users()
        assert list(users).count("919000000103") == 1

    async def test_an_unknown_language_defaults_to_english(self):
        await _touch("919000000104", None)
        assert (await _users())["919000000104"] == "en"


class TestLanguageIsNotClobbered:
    async def test_a_message_with_no_language_keeps_the_remembered_one(self):
        """The failure this prevents: somebody who has written in Hindi for a
        week sends a photo, we learn nothing from it, and their next alert
        arrives in English.

        `touch_user` writes a language only when it actually knows one.
        """
        await _touch("919000000105", "hi")
        await _touch("919000000105", None)
        assert (await _users())["919000000105"] == "hi"

    async def test_a_new_language_does_replace_the_old_one(self):
        """Someone switching languages is a real event, not noise."""
        await _touch("919000000106", "hi")
        await _touch("919000000106", "mr")
        assert (await _users())["919000000106"] == "mr"
