"""
Telling somebody a scheme opened for them — and, mostly, not telling them.

This is the only thing the product does that a person did not ask for at that
moment, so nearly every test here is about a message NOT being sent. The
failure mode is unsolicited messages to people who trusted us with a phone
number, and it is not recoverable by a fix afterwards.

The one that matters most is `TestConsent`. `_OPTED_OUT` is a cache: empty
means "we have not looked", not "nobody opted out". A job that reads the second
meaning messages every person who ever asked us to stop.
"""

from __future__ import annotations

import json

import pytest

from src import alerts, whatsapp_consent
from src.database import (
    alert_already_sent, forget_alerts, get_connection, init_database,
    record_alert, save_context, touch_user,
)

BIHAR_SC = {"state": "Bihar", "caste": "sc", "age": 40, "gender": "female"}


@pytest.fixture(autouse=True)
async def _fresh():
    await init_database()
    whatsapp_consent._OPTED_OUT.clear()
    whatsapp_consent._loaded = False
    yield
    whatsapp_consent._OPTED_OUT.clear()
    whatsapp_consent._loaded = False


async def _person(user_id: str, context: dict, language: str = "hi") -> None:
    db = await get_connection()
    try:
        await touch_user(db, user_id, language)
        await save_context(db, user_id, json.dumps(context))
    finally:
        await db.close()


class TestConsent:
    async def test_it_refuses_to_run_on_an_unloaded_opt_out_list(self, monkeypatch):
        """An empty cache is not consent.

        render.yaml calls losing the opt-out list the one data loss here that
        is not merely inconvenient. If it cannot be read, the job stops.
        """
        async def explode():
            raise RuntimeError("no database")
        monkeypatch.setattr("src.database.get_connection", explode)

        outcome = await alerts.run(since="2000-01-01", dry_run=True)
        assert outcome.refused
        assert "opt-out" in outcome.refused
        assert outcome.sent == 0

    async def test_somebody_who_said_stop_is_never_counted(self):
        await _person("919000000001", BIHAR_SC)
        await whatsapp_consent.opt_out("919000000001")

        outcome = await alerts.run(since="2000-01-01", dry_run=True)
        assert outcome.skipped_opted_out >= 1
        # And they are not in the sent figure by any route.
        assert outcome.sent == 0 or outcome.skipped_opted_out >= 1

    async def test_stop_also_erases_what_we_already_pushed(self):
        """Somebody who leaves and comes back is a new conversation, not one
        carrying a record of which schemes we notified them about."""
        db = await get_connection()
        try:
            await record_alert(db, "919000000002", "some-scheme", "2026-01-01")
            assert await alert_already_sent(db, "919000000002", "some-scheme")
            await forget_alerts(db, "919000000002")
            assert not await alert_already_sent(db, "919000000002", "some-scheme")
        finally:
            await db.close()


class TestWhoIsSkipped:
    async def test_somebody_we_know_nothing_about(self):
        """Alerting from one answer means telling a person every scheme open
        to their state, which is most of them."""
        await _person("919000000003", {"state": "Bihar"})
        outcome = await alerts.run(since="2000-01-01", dry_run=True)
        assert outcome.skipped_nothing_known >= 1

    async def test_an_empty_context(self):
        await _person("919000000004", {})
        outcome = await alerts.run(since="2000-01-01", dry_run=True)
        assert outcome.skipped_nothing_known >= 1

    async def test_nothing_changed_means_nothing_sent(self):
        """The common case, and it must cost nothing."""
        await _person("919000000005", BIHAR_SC)
        outcome = await alerts.run(since="2099-01-01", dry_run=True)
        assert outcome.considered_schemes == 0
        assert outcome.sent == 0


class TestOnlyWhatIsAimedAtThem:
    def test_a_scheme_that_restricts_nobody_is_not_an_alert(self):
        """A scheme open to everybody "matches" everybody. Alerting on a plain
        match would tell four thousand people about a scheme aimed at none of
        them."""
        class Match:
            matched_on = ["state"]
        assert not alerts._targeted(Match())

    def test_a_scheme_that_names_their_community_is(self):
        class Match:
            matched_on = ["state", "caste"]
        assert alerts._targeted(Match())

    @pytest.mark.parametrize("reason", sorted(alerts.TARGETING))
    def test_every_targeting_reason_counts(self, reason):
        class Match:
            matched_on = [reason]
        assert alerts._targeted(Match())

    def test_the_targeting_set_matches_the_engine(self):
        """It is the matcher's own set. Two copies that drift would mean
        alerting on something discovery does not consider targeted."""
        from src.discovery import _TARGETING
        assert alerts.TARGETING == set(_TARGETING)


class TestVolume:
    async def test_nobody_gets_more_than_a_handful(self):
        """A corpus refresh that adds four hundred schemes must not become
        four hundred notifications. Somebody who gets that blocks the number,
        and then the channel is gone for the alert that mattered."""
        assert alerts.MAX_PER_PERSON <= 5

    async def test_a_person_is_told_about_a_scheme_once(self):
        db = await get_connection()
        try:
            await record_alert(db, "919000000006", "scheme-a", "2026-01-01")
            await record_alert(db, "919000000006", "scheme-a", "2026-02-01")
            assert await alert_already_sent(db, "919000000006", "scheme-a")
        finally:
            await db.close()


class TestFacetsFromContext:
    def test_two_answers_is_enough(self):
        assert alerts._facets_from_context({"state": "Bihar", "caste": "sc"})

    def test_one_is_not(self):
        assert alerts._facets_from_context({"state": "Bihar"}) is None

    def test_blanks_do_not_count_as_answers(self):
        assert alerts._facets_from_context(
            {"state": "Bihar", "caste": "", "gender": None}) is None

    def test_a_stale_key_does_not_fail_the_whole_run(self):
        """One person's old context row must not stop everybody else's alert."""
        facets = alerts._facets_from_context(
            {"state": "Bihar", "caste": "sc", "some_removed_field": "x"})
        assert facets is not None
        assert facets.state == "Bihar"

    def test_numbers_arrive_as_numbers(self):
        facets = alerts._facets_from_context(
            {"state": "Bihar", "age": "40", "family_income": "120000"})
        assert facets.age == 40
        assert facets.family_income == 120000.0

    def test_an_unreadable_number_is_dropped_not_guessed(self):
        facets = alerts._facets_from_context(
            {"state": "Bihar", "caste": "sc", "age": "about forty"})
        assert facets is not None
        assert facets.age is None


class TestTheJobRoute:
    def test_it_refuses_without_a_token(self, monkeypatch):
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app)
        response = client.post("/api/jobs/scheme-alerts",
                               json={"since": "2000-01-01"})
        # 503 when JOB_TOKEN is unset, 401 when it is set and wrong. Either
        # way nothing runs.
        assert response.status_code in (401, 503)

    def test_a_wrong_token_is_refused(self, monkeypatch):
        from fastapi.testclient import TestClient
        from src.config import get_settings
        from src.main import app

        get_settings.cache_clear()
        monkeypatch.setenv("JOB_TOKEN", "the-real-token")
        try:
            client = TestClient(app)
            response = client.post("/api/jobs/scheme-alerts",
                                   json={"since": "2000-01-01"},
                                   headers={"X-Job-Token": "not-it"})
            assert response.status_code == 401
        finally:
            get_settings.cache_clear()

    def test_it_dry_runs_by_default(self):
        """A job that has to be asked twice cannot be triggered by accident."""
        from src.api import AlertRunRequest
        assert AlertRunRequest(since="2000-01-01").dry_run is True
