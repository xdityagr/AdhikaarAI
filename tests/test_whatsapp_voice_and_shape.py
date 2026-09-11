"""
How a WhatsApp message looks, and what a voice note gets told back.

These cover the two things a screenshot caught that the test suite did not:

- One reply carried the model's prose AND a bulleted repeat of the same four
  schemes, because the brain appended the cards to the text unconditionally.
  On the website that pairing is right — the cards are separate UI. On WhatsApp
  they land in the same bubble, and the reader sees the same list twice.
- The consent notice was three English paragraphs sitting ABOVE the answer, so
  WhatsApp folded the actual advice behind "Read more".

Both are about bytes on a phone screen, so both are asserted on the string that
would be sent, not on intent.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src import whatsapp_consent as consent
from src.speech import Transcript
from src.worker import ECHO_CHARS, MessageWorker, _echo


@pytest.fixture
def worker():
    instance = MessageWorker(asyncio.Queue())
    instance._rate_limiter.allow = lambda user_id: True
    return instance


class TestHeardEcho:
    def test_the_transcript_is_echoed_on_one_line(self):
        assert _echo("मुझे पेंशन चाहिए") == '🎤 _"मुझे पेंशन चाहिए"_'

    def test_a_long_transcript_is_cut_short(self):
        """The echo is a footnote to the answer, not a competitor to it."""
        line = _echo("hello there " * 40)
        assert len(line) < ECHO_CHARS + 20
        assert line.endswith('…"_')

    def test_line_breaks_in_the_transcript_do_not_break_the_line(self):
        assert "\n" not in _echo("I need\na  pension\n\nplease")

    @pytest.mark.asyncio
    async def test_a_voice_note_is_answered_with_what_we_heard(self, worker):
        """A misheard number produces a confident answer to the wrong question.
        Echoing one line is what lets the person catch that themselves."""
        with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
             patch("src.worker.meta") as sender, \
             patch("src.worker.speech") as speech:
            speech.is_available.return_value = True
            sender.fetch_media = AsyncMock(return_value=(b"audio", "audio/ogg"))
            speech.transcribe = AsyncMock(return_value=Transcript(
                text="मुझे पेंशन चाहिए", ok=True, language="hi", provider="sarvam",
            ))
            brain.return_value = "✅ आपके लिए 3 योजनाएं हैं।"
            sender.send_text = AsyncMock(return_value=True)

            await worker._process_message(
                {"from_number": "u1", "body": "", "message_sid": "v1",
                 "media_id": "M1", "media_type": "audio/ogg"}, 1,
            )

            body = sender.send_text.await_args.kwargs["body"]
            assert body.startswith('🎤 _"मुझे पेंशन चाहिए"_')
            assert "✅ आपके लिए 3 योजनाएं हैं।" in body

    @pytest.mark.asyncio
    async def test_a_typed_message_gets_no_echo(self, worker):
        """Echoing text back to someone who typed it is noise."""
        with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
             patch("src.worker.meta") as sender:
            brain.return_value = "✅ Three schemes match."
            sender.send_text = AsyncMock(return_value=True)

            await worker._process_message(
                {"from_number": "u2", "body": "pension", "message_sid": "t1"}, 1,
            )

            assert "🎤" not in sender.send_text.await_args.kwargs["body"]


class TestMessageShape:
    @pytest.mark.asyncio
    async def test_the_cards_are_not_repeated_under_the_model_s_own_words(self):
        """The failure this exists to prevent: the same schemes twice in one
        bubble, once in sentences and once as a list."""
        from src import whatsapp_brain

        reply = type("R", (), {
            "used_model": True,
            "text": "✅ **Mahila Samridhi Yojana** — business loan.",
            "cards": [{"kind": "scheme_list", "items": [
                {"name": "Mahila Samridhi Yojana"},
            ]}],
        })()

        with patch("src.whatsapp_brain.agent_respond",
                   new_callable=AsyncMock, return_value=reply):
            out = await whatsapp_brain._agent_reply("u3", "hello", "en")

        assert out.count("Mahila Samridhi Yojana") == 1

    @pytest.mark.asyncio
    async def test_cards_still_carry_the_answer_when_the_model_wrote_nothing(self):
        """They are a fallback, not dead code — an empty reply must not mean an
        empty message."""
        from src import whatsapp_brain

        reply = type("R", (), {
            "used_model": True,
            "text": "",
            "cards": [{"kind": "scheme_list", "items": [
                {"name": "Mahila Samridhi Yojana"},
            ]}],
        })()

        with patch("src.whatsapp_brain.agent_respond",
                   new_callable=AsyncMock, return_value=reply):
            out = await whatsapp_brain._agent_reply("u4", "hello", "en")

        assert "Mahila Samridhi Yojana" in out

    def test_the_whatsapp_prompt_never_points_at_a_screen(self):
        """The web prompt tells the model the schemes are already on screen as
        cards. Sent to WhatsApp, that produced a reply saying the schemes were
        "showing above on the screen" to someone whose screen held nothing."""
        from src.agent import SHAPE_WEB, SHAPE_WHATSAPP

        # The web prompt asserts the schemes are already visible; that claim is
        # true there and false on WhatsApp.
        assert "already on the screen" in SHAPE_WEB.lower()
        assert "already on the screen" not in SHAPE_WHATSAPP.lower()

        # WhatsApp's says the opposite, and names the words that broke it.
        whatsapp = SHAPE_WHATSAPP.lower()
        assert "no cards here" in whatsapp
        assert "never say" in whatsapp
        for pointer in ('"above"', '"on the screen"'):
            assert pointer in whatsapp, f"{pointer} is not forbidden"

    def test_the_channel_picks_the_shape(self):
        """A default of "web" keeps every existing caller unchanged; only
        WhatsApp opts into the other one."""
        import inspect
        from src.agent import respond, stream

        for entry in (stream, respond):
            assert inspect.signature(entry).parameters["channel"].default == "web"


class TestConsentNotice:
    def test_the_notice_is_short_enough_to_sit_under_an_answer(self):
        """At 380 characters and three paragraphs it pushed the answer itself
        behind WhatsApp's "Read more" fold."""
        for code, text in consent.NOTICES.items():
            assert len(text) < 220, f"{code} notice is {len(text)} chars"

    def test_every_app_language_has_one(self):
        from src.i18n import LANGUAGES
        assert set(consent.NOTICES) == set(LANGUAGES)

    def test_each_one_keeps_the_three_things_that_matter(self):
        """Shortening the notice must not quietly drop its substance: what the
        data is for, that we never ask for money, and how to stop."""
        for code, text in consent.NOTICES.items():
            assert "STOP" in text, f"{code} has no way to opt out"
            assert "_" in text, f"{code} is not rendered as an aside"

    def test_the_notice_arrives_in_the_person_s_own_language(self):
        assert consent.notice("hi") == consent.NOTICES["hi"]
        assert consent.notice("ta") == consent.NOTICES["ta"]

    def test_an_unknown_language_still_gets_a_notice(self):
        """A missing translation must never mean no privacy notice at all."""
        assert consent.notice("xx") == consent.NOTICES["en"]
        assert consent.notice(None) == consent.NOTICES["en"]

    @pytest.mark.asyncio
    async def test_it_goes_under_the_answer_not_over_it(self):
        from src import whatsapp_brain

        whatsapp_brain._CONTEXT.pop("u5", None)
        with patch("src.whatsapp_brain.agent_available", return_value=True), \
             patch("src.whatsapp_brain._agent_reply",
                   new_callable=AsyncMock, return_value="✅ Three schemes match."):
            out = await whatsapp_brain.reply("u5", "hello")

        assert out.index("Three schemes match") < out.index("STOP")

    @pytest.mark.asyncio
    async def test_it_is_sent_only_once(self):
        from src import whatsapp_brain

        whatsapp_brain._CONTEXT.pop("u6", None)
        with patch("src.whatsapp_brain.agent_available", return_value=True), \
             patch("src.whatsapp_brain._agent_reply",
                   new_callable=AsyncMock, return_value="✅ Answer."):
            first = await whatsapp_brain.reply("u6", "hello")
            second = await whatsapp_brain.reply("u6", "and housing?")

        assert "STOP" in first
        assert "STOP" not in second

class TestMediaPaths:
    """A rendered map is a picture. Its path reached a real phone as the
    literal line "/media/b6qNqD325DuGUa70Bo7mRQ.png" — not openable, not a
    map, and indistinguishable from the assistant breaking."""

    def test_a_path_on_its_own_line_is_removed(self):
        from src.whatsapp_brain import strip_media_paths
        assert strip_media_paths(
            "Here is the map:\n/media/b6qNqD325DuGUa70Bo7mRQ.png"
        ) == "Here is the map:"

    def test_a_path_mid_sentence_is_removed(self):
        from src.whatsapp_brain import strip_media_paths
        assert "/media/" not in strip_media_paths(
            "See /media/abcdefghij1234567890.png for the office")

    def test_an_office_name_with_a_slash_survives(self):
        from src.whatsapp_brain import strip_media_paths
        name = "Rajasthan SC/ST Finance & Development Co-operative Corporation"
        assert strip_media_paths(name) == name

    def test_a_real_url_survives(self):
        """Scheme pages are worth linking; only our own media plumbing is not."""
        from src.whatsapp_brain import strip_media_paths
        assert "nsfdc.nic.in" in strip_media_paths("Visit https://nsfdc.nic.in")

    def test_the_prompt_forbids_writing_one(self):
        from src.agent import SHAPE_WHATSAPP
        flat = " ".join(SHAPE_WHATSAPP.lower().split())
        assert "never write a file path" in flat

    def test_the_wire_strips_it_too(self):
        """Both reply builders strip it; this is the gate nothing routes around."""
        import inspect
        from src import meta_whatsapp
        source = inspect.getsource(meta_whatsapp.send_text)
        assert "strip_media_paths(body)" in source
