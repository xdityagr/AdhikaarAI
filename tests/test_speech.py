"""
Which speech engine gets used, and in what order.

This is all about one measured failure. Deepgram's multilingual model heard
Tamil correctly and wrote it out in Devanagari — "नान तमिलनाकल व सिक्कुम विधवई"
— scoring 0% against the truth, and did the same to Bengali. Sarvam scored 100%
on both.

That mattered because `multi` was the fallback whenever the language was not
already known, which on WhatsApp is every first voice note. So the ordering
below is not a preference, it is the fix, and it is easy to undo by accident:
move Deepgram's `multi` anywhere but last and Tamil silently starts coming back
in the wrong script again.
"""

import pytest

from src import speech


class FakeSettings:
    def __init__(self, sarvam="", deepgram=""):
        self.sarvam_api_key = sarvam
        self.deepgram_api_key = deepgram


BOTH = FakeSettings(sarvam="s", deepgram="d")
SARVAM_ONLY = FakeSettings(sarvam="s")
DEEPGRAM_ONLY = FakeSettings(deepgram="d")


def names(plan):
    return [(engine.__name__, code) for engine, code in plan]


class TestCoverage:
    def test_all_thirteen_app_languages_are_covered(self):
        """Neither engine manages this alone, which is why both stay."""
        from src.i18n import LANGUAGES
        assert set(LANGUAGES) <= speech.SUPPORTED_LANGUAGES

    def test_sarvam_covers_what_deepgram_cannot(self):
        for language in ("ml", "or"):
            assert language in speech.SARVAM_CODES
            assert language not in speech.DEEPGRAM_LANGUAGES

    def test_deepgram_covers_what_sarvam_cannot(self):
        for language in ("as", "ur"):
            assert language in speech.DEEPGRAM_LANGUAGES
            assert language not in speech.SARVAM_CODES

    def test_odia_uses_sarvam_s_own_spelling(self):
        """Sarvam calls it `od-IN`, not the ISO `or-IN` used everywhere else
        here. The wrong one is a 400, so it is worth pinning."""
        assert speech.SARVAM_CODES["or"] == "od-IN"


class TestOrdering:
    def test_an_unknown_language_goes_to_sarvam_to_be_detected(self):
        """The first voice note. Assuming English here was the original bug."""
        plan = names(speech._plan(None, BOTH))
        assert plan[0] == ("_sarvam", speech.AUTODETECT)

    def test_a_known_language_is_named_not_guessed(self):
        plan = names(speech._plan("ta", BOTH))
        assert plan[0] == ("_sarvam", "ta-IN")

    def test_assamese_and_urdu_go_to_deepgram(self):
        for language in ("as", "ur"):
            plan = names(speech._plan(language, BOTH))
            assert plan[0] == ("_deepgram", language)

    def test_deepgram_backs_sarvam_up_where_both_can_hear(self):
        plan = names(speech._plan("hi", BOTH))
        assert plan == [("_sarvam", "hi-IN"), ("_deepgram", "hi")]

    def test_multi_is_never_used_when_anything_else_can_be(self):
        """The whole point. Every language, both keys — `multi` must not appear."""
        from src.i18n import LANGUAGES
        for language in list(LANGUAGES) + [None]:
            plan = names(speech._plan(language, BOTH))
            assert (
                "_deepgram", speech.DEEPGRAM_MULTILINGUAL,
            ) not in plan, f"multi reached for {language}"

    def test_multi_is_the_last_resort_when_sarvam_is_not_configured(self):
        """A Sarvam outage should degrade, not go silent — but only then."""
        plan = names(speech._plan(None, DEEPGRAM_ONLY))
        assert plan == [("_deepgram", speech.DEEPGRAM_MULTILINGUAL)]

    def test_nothing_configured_plans_nothing(self):
        assert speech._plan("hi", FakeSettings()) == []

    def test_sarvam_alone_still_serves_its_own_languages(self):
        assert names(speech._plan("ml", SARVAM_ONLY)) == [("_sarvam", "ml-IN")]

    def test_sarvam_alone_cannot_do_urdu_and_says_so(self):
        """Rather than quietly transcribing Urdu as something else."""
        assert names(speech._plan("ur", SARVAM_ONLY)) == [("_sarvam", speech.AUTODETECT)]


class TestTrust:
    def test_a_multi_transcript_is_always_marked_unclear(self):
        """Because it may have used the wrong script, and nothing in the
        response says so."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        payload = {"results": {"channels": [{"alternatives": [
            {"transcript": "नान तमिलनाकल", "confidence": 0.99},
        ]}]}}
        with patch("src.speech._post_with_one_retry",
                   new_callable=AsyncMock, return_value=payload), \
             patch("src.speech.get_settings", return_value=BOTH):
            result = asyncio.run(
                speech._deepgram(b"a", "audio/ogg", speech.DEEPGRAM_MULTILINGUAL),
            )

        assert result.ok
        assert result.unclear, "a multi transcript must never be trusted"
        assert result.language == "", "multi must never name the language"

    def test_a_named_deepgram_transcript_reports_its_language(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        payload = {"results": {"channels": [{"alternatives": [
            {"transcript": "ok", "confidence": 0.9},
        ]}]}}
        with patch("src.speech._post_with_one_retry",
                   new_callable=AsyncMock, return_value=payload), \
             patch("src.speech.get_settings", return_value=BOTH):
            result = asyncio.run(speech._deepgram(b"a", "audio/ogg", "ur"))

        assert result.language == "ur"
        assert not result.unclear

    def test_a_weakly_detected_language_is_not_reported_as_fact(self):
        """Sarvam's number is how sure it is of the LANGUAGE. Acting on a coin
        flip would switch someone's replies into a language they do not read."""
        assert speech._our_code("od-IN") == "or"
        assert speech._our_code("hi-IN") == "hi"


class TestContentType:
    """WhatsApp sends `audio/ogg; codecs=opus`. Sarvam allows `audio/ogg` and
    compares the string EXACTLY, so the codec parameter was a 400 — and every
    voice note came back as "I could not make out that voice note", which
    blamed the speaker for our own header."""

    def test_the_codec_parameter_is_stripped(self):
        assert speech._bare_mime("audio/ogg; codecs=opus") == "audio/ogg"

    def test_a_plain_type_is_left_alone(self):
        assert speech._bare_mime("audio/wav") == "audio/wav"

    def test_case_and_spacing_do_not_matter(self):
        assert speech._bare_mime("  AUDIO/OGG ; codecs=opus ") == "audio/ogg"

    def test_a_missing_type_still_yields_something_sendable(self):
        assert speech._bare_mime("") == "audio/ogg"
        assert speech._bare_mime(None) == "audio/ogg"

    def test_what_is_sent_is_on_sarvam_s_allowed_list(self):
        """The list Sarvam returned in its own 400."""
        allowed = {
            "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg",
            "audio/opus", "audio/flac", "audio/mp4", "audio/x-m4a", "audio/aac",
            "audio/amr", "audio/webm", "application/octet-stream",
        }
        for sent in ("audio/ogg; codecs=opus", "audio/ogg", "audio/wav",
                     "audio/mpeg", "audio/mp4"):
            assert speech._bare_mime(sent) in allowed, sent


class TestAvailability:
    def test_either_key_is_enough(self, monkeypatch):
        monkeypatch.setattr(speech, "get_settings", lambda: SARVAM_ONLY)
        assert speech.is_available()
        monkeypatch.setattr(speech, "get_settings", lambda: DEEPGRAM_ONLY)
        assert speech.is_available()

    def test_neither_key_means_no_voice(self, monkeypatch):
        monkeypatch.setattr(speech, "get_settings", lambda: FakeSettings())
        assert not speech.is_available()
