"""
The inbound voice channel.

Three properties are load-bearing, and each of them is a way a real person gets
hurt if it stops holding:

- **Every route refuses an unsigned request.** These endpoints run the matching
  engine, and they are being added at a time when nothing else in this API has
  auth in front of it. An open one is a stranger's free compute at best and a
  way to probe the corpus at worst.
- **The voice answer and the web answer are the same answer.** The tool
  endpoints wrap `TOOL_IMPLEMENTATIONS` rather than reimplementing matching, so
  the two channels cannot drift into telling one person two different things —
  which is the kind of bug nobody finds until it has already happened.
- **An unreadable answer is asked again, never recorded as a skip.** On a call
  there is no screen to catch a misheard answer on, so a mishearing silently
  filed as "declined to say" produces results that do not reflect what the
  person actually said.

Plus the decision the handoff asked to be written down rather than defaulted:
calls are not recorded.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from src import interview
from src import voice
from src import whatsapp_brain as brain
from src import whatsapp_consent as consent
from src.agent import TOOL_IMPLEMENTATIONS
from src.config import get_settings
from src.main import app

SECRET = "test-voice-secret"


@pytest.fixture(autouse=True)
def voice_settings(monkeypatch):
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "vapi_webhook_secret", SECRET, raising=False)
    monkeypatch.setattr(settings, "voice_verify_signatures", True, raising=False)
    voice._ASKED.clear()
    brain._CONTEXT.clear()
    brain._LOADED.clear()
    consent._OPTED_OUT.clear()
    yield settings
    voice._ASKED.clear()
    brain._CONTEXT.clear()
    brain._LOADED.clear()
    consent._OPTED_OUT.clear()
    get_settings.cache_clear()


@pytest.fixture
def client():
    # No lifespan: these routes must work without the worker, and starting it
    # would make every test in this module wait on a queue it never uses.
    return TestClient(app)


def envelope(name: str, arguments: dict | None = None,
             number: str = "+91 90000 00201", call_id: str = "tc_1") -> bytes:
    """What the provider POSTs, as bytes — signatures are over bytes."""
    return json.dumps({
        "message": {
            "type": "tool-calls",
            "timestamp": int(time.time() * 1000),
            "toolCallList": [
                {"id": call_id, "name": name, "arguments": arguments or {}},
            ],
            "call": {"id": "call_1", "customer": {"number": number}},
        },
    }).encode()


def signed(body: bytes) -> dict:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"x-vapi-signature": digest, "content-type": "application/json"}


def result_of(response) -> dict:
    """The single tool result, unwrapped from the provider's envelope."""
    body = response.json()
    assert "results" in body, body
    return json.loads(body["results"][0]["result"])


# ---------------------------------------------------------------------------
# Nobody gets in without a signature
# ---------------------------------------------------------------------------

VOICE_ROUTES = [
    ("POST", "/api/voice/tools/find_schemes"),
    ("POST", "/api/voice/tools/check_scheme_eligibility"),
    ("POST", "/api/voice/tools/find_offices"),
    ("POST", "/api/voice/tools/next_question"),
    ("POST", "/api/voice/tools/answer_question"),
    ("POST", "/api/voice/events"),
]


class TestNothingUnsignedGetsThrough:
    @pytest.mark.parametrize("method,path", VOICE_ROUTES)
    def test_every_route_rejects_an_unsigned_request(self, client, method, path):
        response = client.request(method, path, content=envelope("find_schemes"))
        assert response.status_code == 403, f"{path} answered an unsigned request"

    @pytest.mark.parametrize("method,path", VOICE_ROUTES)
    def test_every_route_rejects_a_wrong_signature(self, client, method, path):
        body = envelope("find_schemes")
        response = client.request(
            method, path, content=body,
            headers={"x-vapi-signature": "0" * 64},
        )
        assert response.status_code == 403, f"{path} accepted a bad signature"

    def test_a_signature_over_different_bytes_fails(self, client):
        """Re-serialising the JSON changes the bytes, and must fail loudly."""
        body = envelope("corpus_stats")
        tampered = body.replace(b"corpus_stats", b"find_schemes")
        response = client.post("/api/voice/tools/find_schemes",
                               content=tampered, headers=signed(body))
        assert response.status_code == 403

    def test_a_shared_secret_header_is_accepted(self, client):
        """The legacy credential type sends a static secret, not an HMAC."""
        body = envelope("corpus_stats")
        response = client.post("/api/voice/tools/corpus_stats", content=body,
                               headers={"x-vapi-secret": SECRET})
        assert response.status_code == 200

    def test_a_bearer_token_is_accepted(self, client):
        body = envelope("corpus_stats")
        response = client.post("/api/voice/tools/corpus_stats", content=body,
                               headers={"authorization": f"Bearer {SECRET}"})
        assert response.status_code == 200

    def test_a_wrong_shared_secret_is_not(self, client):
        body = envelope("corpus_stats")
        response = client.post("/api/voice/tools/corpus_stats", content=body,
                               headers={"x-vapi-secret": "not-the-secret"})
        assert response.status_code == 403

    def test_a_bad_hmac_never_falls_through_to_the_weaker_check(self, client):
        """Or the weaker check becomes a way around the stronger one."""
        body = envelope("corpus_stats")
        response = client.post(
            "/api/voice/tools/corpus_stats", content=body,
            headers={"x-vapi-signature": "0" * 64, "x-vapi-secret": SECRET},
        )
        assert response.status_code == 403

    def test_no_configured_secret_means_no_service(self, voice_settings, client):
        """Fail closed. An unsigned endpoint running the engine is worse than
        an endpoint that is switched off."""
        voice_settings.vapi_webhook_secret = ""
        response = client.post("/api/voice/tools/corpus_stats",
                               content=envelope("corpus_stats"),
                               headers={"x-vapi-secret": ""})
        assert response.status_code == 403

    def test_a_stale_signed_timestamp_is_a_replay(self, client):
        body = envelope("corpus_stats")
        old = str(int((time.time() - 3600) * 1000))
        digest = hmac.new(SECRET.encode(), f"{old}.".encode() + body,
                          hashlib.sha256).hexdigest()
        response = client.post(
            "/api/voice/tools/corpus_stats", content=body,
            headers={"x-vapi-signature": digest,
                     "x-vapi-signature-timestamp": old},
        )
        assert response.status_code == 403

    def test_a_fresh_signed_timestamp_is_fine(self, client):
        body = envelope("corpus_stats")
        now = str(int(time.time() * 1000))
        digest = hmac.new(SECRET.encode(), f"{now}.".encode() + body,
                          hashlib.sha256).hexdigest()
        response = client.post(
            "/api/voice/tools/corpus_stats", content=body,
            headers={"x-vapi-signature": digest,
                     "x-vapi-signature-timestamp": now},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# The voice path cannot drift from the web path
# ---------------------------------------------------------------------------

class TestSameAnswerAsTheWeb:
    """Both channels must answer from the same computation.

    Not "a similar answer" — the same one. A person who checks on the website
    what they were told on the phone has to find it there.
    """

    @pytest.mark.parametrize("name,arguments", [
        ("corpus_stats", {}),
        ("find_schemes", {"caste": "sc", "state": "Bihar", "gender": "female"}),
        ("search_schemes", {"query": "widow pension"}),
    ])
    def test_the_endpoint_returns_the_implementation_s_own_summary(
            self, client, name, arguments):
        body = envelope(name, arguments)
        response = client.post(f"/api/voice/tools/{name}",
                               content=body, headers=signed(body))
        assert response.status_code == 200

        _payload, _cards, summary = TOOL_IMPLEMENTATIONS[name](**arguments)
        assert result_of(response)["say"] == summary

    def test_the_counts_are_carried_through_untouched(self, client):
        """The numbers are computed, never generated. Trimming what is read
        aloud must not touch them."""
        arguments = {"caste": "sc", "state": "Bihar"}
        body = envelope("find_schemes", arguments)
        response = client.post("/api/voice/tools/find_schemes",
                               content=body, headers=signed(body))

        payload, _cards, _summary = TOOL_IMPLEMENTATIONS["find_schemes"](**arguments)
        detail = result_of(response)["detail"]
        for key in ("total_matched", "aimed_at_this_person", "considered"):
            assert detail[key] == payload[key]

    def test_a_long_list_is_cut_for_speech_but_says_so(self, client):
        """A list of forty schemes is not a sentence."""
        body = envelope("find_schemes", {"state": "Bihar"})
        response = client.post("/api/voice/tools/find_schemes",
                               content=body, headers=signed(body))
        detail = result_of(response)["detail"]
        matches = detail.get("top_matches") or []
        assert len(matches) <= voice.SPOKEN_ITEMS
        if "top_matches_total" in detail:
            assert detail["top_matches_total"] >= len(matches)

    def test_the_tool_call_id_comes_back(self, client):
        """The provider matches the result to the call by this id."""
        body = envelope("corpus_stats", call_id="tc_xyz")
        response = client.post("/api/voice/tools/corpus_stats",
                               content=body, headers=signed(body))
        assert response.json()["results"][0]["toolCallId"] == "tc_xyz"

    def test_arguments_sent_as_a_json_string_still_work(self, client):
        """A model serialises a nested object as text often enough that it
        cannot be treated as an exception — `agent._clean_args` exists for the
        same reason."""
        payload = json.dumps({
            "message": {
                "type": "tool-calls",
                "toolCallList": [{"id": "t1", "name": "search_schemes",
                                  "arguments": json.dumps({"query": "pension"})}],
                "call": {"customer": {"number": "+919000000201"}},
            },
        }).encode()
        response = client.post("/api/voice/tools/search_schemes",
                               content=payload, headers=signed(payload))
        assert response.status_code == 200
        assert "could not look that up" not in result_of(response)["say"].lower()


# ---------------------------------------------------------------------------
# What a phone call may and may not do
# ---------------------------------------------------------------------------

class TestWhatTheCallWillNotDo:
    def test_the_application_form_is_not_read_down_the_phone(self, client):
        """Eleven fields, read aloud, is worse than every alternative —
        including sending it to WhatsApp and reading out a handoff code."""
        body = envelope("prepare_application", {"slug": "sui"})
        response = client.post("/api/voice/tools/prepare_application",
                               content=body, headers=signed(body))
        assert response.status_code == 200
        said = result_of(response)["say"].lower()
        assert "whatsapp" in said
        assert result_of(response)["detail"]["refused"] == "prepare_application"

    def test_prepare_application_is_not_in_the_allowed_set(self):
        assert "prepare_application" not in voice.ALLOWED
        assert "prepare_application" in voice.REFUSED

    def test_an_unknown_tool_is_a_404_not_a_guess(self, client):
        body = envelope("summon_a_verdict")
        response = client.post("/api/voice/tools/summon_a_verdict",
                               content=body, headers=signed(body))
        assert response.status_code == 404

    def test_calls_are_not_recorded(self):
        """Decided and written down, per Task 3 — not left to a default.

        Turning this on is not a config change: it needs a spoken notice in
        every language before the first word is captured, a retention period
        and a deletion path.
        """
        assert voice.RECORDING_POLICY == "none"

    def test_nothing_asks_for_the_numbers_a_scammer_asks_for(self):
        """The fraud pattern this audience suffers most is a phone call asking
        for exactly these. A real service that asks the same questions teaches
        people that the scam is normal."""
        spoken = " ".join(
            [voice.REFUSED["prepare_application"]]
            + [text for text, _ in [voice.next_question("919000000999")]]
        ).lower()
        for forbidden in voice.NEVER_ASK:
            assert forbidden not in spoken


# ---------------------------------------------------------------------------
# The adaptive interview — the most voice-native thing we have
# ---------------------------------------------------------------------------

class TestTheInterview:
    def test_it_asks_one_question_at_a_time(self, client):
        body = envelope("next_question")
        response = client.post("/api/voice/tools/next_question",
                               content=body, headers=signed(body))
        assert response.status_code == 200
        detail = result_of(response)["detail"]
        assert detail["finished"] is False
        assert detail["question_id"]
        assert detail["prompt"]

    def test_the_same_question_is_not_asked_twice(self, client):
        body = envelope("next_question")
        first = client.post("/api/voice/tools/next_question",
                            content=body, headers=signed(body))
        second = client.post("/api/voice/tools/next_question",
                             content=body, headers=signed(body))
        assert (result_of(first)["detail"]["question_id"]
                != result_of(second)["detail"]["question_id"])

    def test_an_unreadable_answer_is_asked_again_not_skipped(self):
        """The distinction that matters more here than anywhere else.

        A misheard answer recorded as a skip produces results that do not
        reflect what the person said, and they never see a screen to catch it.
        """
        number = "919000000301"
        _say, asked = voice.next_question(number)
        question_id = asked["question_id"]

        say, detail = voice.answer_question(number, question_id,
                                            "mmm crackle static")
        assert detail.get("retry") is True
        assert "again" in say.lower()
        # And it is back in the pool, not filed as declined.
        assert question_id not in voice._ASKED[number]

        _say, again = voice.next_question(number)
        assert again["question_id"] == question_id

    def test_a_real_skip_costs_nothing_and_stops_being_offered(self):
        """`discovery` is built on 'absence is not negation' — an unanswered
        question can never exclude a scheme."""
        number = "919000000302"
        _say, asked = voice.next_question(number)
        question_id = asked["question_id"]

        say, detail = voice.answer_question(number, question_id, "skip")
        assert detail["skipped"] == question_id
        assert "nothing" in say.lower()
        assert question_id in voice._ASKED[number]

        _say, again = voice.next_question(number)
        assert again.get("question_id") != question_id

    def test_an_answer_is_remembered_where_every_channel_can_read_it(self):
        number = "919000000303"
        voice._ASKED[number] = set()

        say, detail = voice.answer_question(number, "caste", "sc")
        assert detail.get("retry") is not True, say
        assert brain._CONTEXT[number]["caste"] == "sc"

    def test_every_question_the_interview_can_ask_is_one_we_keep(self):
        """A hand-written list of durable facets was wrong within an hour: it
        omitted marital status, employment, residence, minority and land, so a
        caller could say "I am a widow", have it used for that one lookup, and
        be asked again on the next call."""
        for question in interview.QUESTIONS:
            assert question.facet_field in voice.DURABLE_FACETS, question.id

    def test_an_answer_no_tool_accepts_is_still_remembered(self):
        """`Facets` carries twenty-one fields and `find_schemes` takes ten.
        The answer must survive the gap rather than crash the lookup."""
        number = "919000000305"
        voice._ASKED[number] = set()

        say, detail = voice.answer_question(number, "marital", "widowed")
        assert detail.get("retry") is not True, say
        assert brain._CONTEXT[number]["marital_status"] == "widowed"

        # And the next lookup for this caller must not raise on it.
        spoken, _detail = voice.run_tool(
            "find_schemes",
            {field: value for field, value in vars(voice.known_facets(number)).items()
             if value not in (None, "", [])},
        )
        assert "could not look that up" not in spoken.lower()

    def test_a_question_we_no_longer_recognise_does_not_crash_the_call(self):
        say, detail = voice.answer_question("919000000304", "no_such_question", "yes")
        assert detail["retry"] is True
        assert say


# ---------------------------------------------------------------------------
# The caller is not a stranger
# ---------------------------------------------------------------------------

class TestCrossChannelMemory:
    async def test_a_whatsapp_user_who_rings_is_recognised(self):
        """Same number, same state, same caste, without being asked again.
        That is the point of the feature, and the table is already there."""
        number = "919000000401"
        brain._CONTEXT[number].update({"state": "Bihar", "caste": "sc",
                                       "language": "hi"})

        facets = voice.known_facets(number)
        assert facets.state == "Bihar"
        assert facets.caste == "sc"
        assert brain.language_if_known(number) == "hi"

    def test_the_number_is_the_key_however_it_is_punctuated(self):
        for written in ("+91 90000 00201", "+919000000201", "919000000201"):
            message = {"call": {"customer": {"number": written}}}
            assert voice.caller_number(message) == "919000000201"

    def test_a_caller_with_no_number_is_still_answered(self, client):
        """A withheld number is a person, not an error."""
        body = json.dumps({
            "message": {"type": "tool-calls",
                        "toolCallList": [{"id": "t", "name": "corpus_stats",
                                          "arguments": {}}]},
        }).encode()
        response = client.post("/api/voice/tools/corpus_stats",
                               content=body, headers=signed(body))
        assert response.status_code == 200

    async def test_what_the_caller_already_said_reaches_the_matcher(self, client):
        """The model should not have to repeat the caller's state back to us."""
        number = "919000000402"
        brain._CONTEXT[number].update({"state": "Bihar", "caste": "sc"})

        body = envelope("find_schemes", {}, number=f"+{number}")
        response = client.post("/api/voice/tools/find_schemes",
                               content=body, headers=signed(body))

        expected, _cards, _summary = TOOL_IMPLEMENTATIONS["find_schemes"](
            state="Bihar", caste="sc")
        assert result_of(response)["detail"]["total_matched"] == expected["total_matched"]

    async def test_somebody_who_said_stop_is_helped_but_not_recorded(self, client):
        """Ringing us is not a retraction of STOP — it is a person who needs
        help now. So the call is answered and leaves no trace."""
        number = "919000000403"
        consent._OPTED_OUT.add(number)
        consent._loaded = True
        try:
            body = envelope("corpus_stats", {}, number=f"+{number}")
            response = client.post("/api/voice/tools/corpus_stats",
                                   content=body, headers=signed(body))
            assert response.status_code == 200
            assert number not in brain._LOADED
        finally:
            consent._loaded = False


# ---------------------------------------------------------------------------
# The call ends
# ---------------------------------------------------------------------------

class TestCallLifecycle:
    def test_hanging_up_forgets_which_questions_were_asked(self, client):
        """A call is a session. The next one must not inherit a half-finished
        question list — but what the person actually told us survives."""
        number = "919000000501"
        voice._ASKED[number] = {"caste", "state"}
        brain._CONTEXT[number]["state"] = "Bihar"

        body = json.dumps({
            "message": {"type": "status-update", "status": "ended",
                        "call": {"customer": {"number": f"+{number}"}}},
        }).encode()
        response = client.post("/api/voice/events", content=body,
                               headers=signed(body))

        assert response.status_code == 200
        assert number not in voice._ASKED
        assert brain._CONTEXT[number]["state"] == "Bihar"

    def test_an_event_we_do_not_act_on_is_still_a_200(self, client):
        """A provider that gets a non-200 retries, and a retried webhook is a
        second answer to a question already answered."""
        body = json.dumps({"message": {"type": "speech-update"}}).encode()
        response = client.post("/api/voice/events", content=body,
                               headers=signed(body))
        assert response.status_code == 200

    def test_malformed_json_does_not_take_the_call_down(self, client):
        response = client.post("/api/voice/tools/corpus_stats",
                               content=b"{not json", headers=signed(b"{not json"))
        assert response.status_code == 200

    def test_health_says_what_is_configured_without_saying_what_it_is(self, client):
        response = client.get("/api/voice/health")
        body = response.json()
        assert body["secret_configured"] is True
        assert SECRET not in json.dumps(body)
        assert body["recording"] == "none"


# ---------------------------------------------------------------------------
# Provisioning — the part that decides what language the phone line speaks
# ---------------------------------------------------------------------------

class TestProvisioning:
    """`scripts/provision_voice.py` encodes what the spike measured.

    These are not tests of Vapi. They are tests that we cannot accidentally
    stand up a phone line that answers in English to a Tamil speaker, which is
    the specific failure the whole phase exists to avoid — a scheme finder that
    only answers in English is the problem this product was built to solve.
    """

    def test_a_language_we_cannot_speak_is_refused(self):
        from scripts import provision_voice as provision
        # Malayalam: Sarvam has it, Vapi's Deepgram does not.
        assert provision.run("ml", "https://example.onrender.com",
                             attach=False, dry_run=True) == 1

    def test_a_language_we_can_hear_but_not_speak_is_refused(self):
        """Bengali transcribes on nova-3 and has no Flash v2.5 voice. Half a
        channel is not a channel — the caller would be understood and then
        answered in English."""
        from scripts import provision_voice as provision
        assert provision.run("bn", "https://example.onrender.com",
                             attach=False, dry_run=True) == 1

    def test_hindi_and_tamil_are_the_two_that_clear(self):
        from scripts import provision_voice as provision
        for language in ("hi", "ta"):
            assert language in provision.VAPI_DEEPGRAM_STT
            assert language in provision.VAPI_ELEVENLABS_TTS

    def test_an_unreachable_base_url_is_refused(self):
        from scripts import provision_voice as provision
        assert provision.run("hi", "http://localhost:8000",
                             attach=False, dry_run=True) == 1

    def test_every_offerable_language_has_a_greeting_in_it(self):
        """A greeting that falls back to English is how an 'multilingual' line
        turns out to open in English every time."""
        from scripts import provision_voice as provision
        for language in provision.VAPI_ELEVENLABS_TTS:
            assert language in provision._GREETING, language

    def test_the_form_filler_is_not_registered_as_a_tool(self):
        """Left out of the assistant entirely, so the model cannot reach for it
        even if it wants to."""
        from scripts import provision_voice as provision
        assert "prepare_application" not in provision._TOOL_ORDER

    def test_every_registered_tool_is_one_the_endpoint_will_serve(self):
        from scripts import provision_voice as provision
        for name in provision._TOOL_ORDER:
            assert name in voice.ALLOWED, name

    def test_recording_is_off_in_the_payload_too(self):
        """Stated, not defaulted — 'we never turned it on' and 'we turned it
        off' are different claims and only one survives a changed default."""
        from scripts import provision_voice as provision
        payload = provision.build("hi", "https://example.onrender.com", "s3cret")
        assert payload["artifactPlan"]["recordingEnabled"] is False

    def test_the_secret_reaches_every_tool(self):
        """One unsigned tool is an open endpoint; a missing secret is a 403 the
        dashboard reports only as 'assistant did not respond'."""
        from scripts import provision_voice as provision
        payload = provision.build("hi", "https://example.onrender.com", "s3cret")
        tools = payload["model"]["tools"]
        assert tools
        for tool in tools:
            assert tool["server"]["secret"] == "s3cret"
            assert tool["server"]["url"].startswith("https://")

    def test_tool_descriptions_are_the_web_s_own(self):
        """Two copies would drift, and then the phone and the website would
        reach for different tools on the same sentence."""
        from scripts import provision_voice as provision
        from src.agent import TOOL_SCHEMAS
        published = {s["name"]: s["description"] for s in TOOL_SCHEMAS}
        payload = provision.build("hi", "https://example.onrender.com", "s3cret")
        for tool in payload["model"]["tools"]:
            name = tool["function"]["name"]
            if name in published:
                assert tool["function"]["description"] == published[name], name


# ---------------------------------------------------------------------------
# The published FAQs — quoted, never composed
# ---------------------------------------------------------------------------

class TestPublishedFaqs:
    """52,394 government-written pairs, and the discipline that makes them safe.

    The corpus holds the ANSWERS in English only. myScheme's API does return a
    per-language FAQ block, but measured over 382 sampled pairs it translates
    100% of the questions and 0% of the answers — so this must never pretend a
    quoted English answer is a translated one.
    """

    def test_it_quotes_the_scheme_s_own_answer(self):
        say, detail = voice.answer_faq("sui", "what is the interest rate", "en")
        assert detail["matched"] is True
        assert detail["quoted"] is True
        # The spoken line IS the published answer, not a paraphrase of it.
        assert say == detail["answer"]

    def test_a_question_the_corpus_does_not_cover_gets_no_answer(self):
        """'We do not know, and here is who does' is a true sentence. A
        confidently-read near-miss is not, and the listener cannot see which
        question it actually answers."""
        say, detail = voice.answer_faq("sui", "zzzz qqqq", "en")
        assert detail["matched"] is False
        assert detail["suggest"] == "find_offices"
        assert "do not cover" in say

    def test_a_non_english_caller_is_told_it_is_a_translation(self):
        _say, detail = voice.answer_faq("sui", "what is the interest rate", "hi")
        assert detail["translate_aloud"] is True
        assert detail["say_it_is_a_translation"] is True
        assert detail["source_language"] == "en"

    def test_an_english_caller_is_not(self):
        _say, detail = voice.answer_faq("sui", "what is the interest rate", "en")
        assert detail["translate_aloud"] is False

    def test_an_unknown_scheme_does_not_invent_one(self):
        say, detail = voice.answer_faq("no-such-scheme", "anything", "en")
        assert detail["found"] is False
        assert "do not have" in say

    def test_the_caller_s_language_comes_from_what_we_already_know(self, client):
        """A returning WhatsApp user does not have to say which language they
        are speaking for the quote to be flagged as a translation."""
        number = "919000000601"
        brain._CONTEXT[number]["language"] = "ta"

        body = envelope("answer_faq",
                        {"slug": "sui", "question": "what is the interest rate"},
                        number=f"+{number}")
        response = client.post("/api/voice/tools/answer_faq",
                               content=body, headers=signed(body))
        assert response.status_code == 200
        assert result_of(response)["detail"]["say_it_is_a_translation"] is True

    def test_faqs_are_english_only_in_the_corpus(self):
        """The fact the whole approach rests on. If a `faqs` column ever appears
        on `scheme_i18n`, this test should fail and the read-time translation
        should be reconsidered — government text beats ours."""
        from src.discovery import open_corpus
        connection = open_corpus()
        if connection is None:
            pytest.skip("corpus not built")
        try:
            columns = {row[1] for row in
                       connection.execute("PRAGMA table_info(scheme_i18n)")}
        finally:
            connection.close()
        assert "faqs" not in columns
