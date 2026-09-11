"""
What the WhatsApp worker does with a message.

Replaces the old button-routing tests, which asserted that the worker ran its
own LangGraph and replied with Twilio Content Templates. Both are gone: WhatsApp
now answers through the same brain as the website, because the channel that
reaches the most people was the one still asking "business loan or education
loan?" — and buttons went with it, since they need pre-approved templates and
the guided flow numbers its options instead, which a person can type or dictate.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.speech import Transcript
from src.worker import MessageWorker


@pytest.fixture
def worker():
    instance = MessageWorker(asyncio.Queue())
    instance._rate_limiter.allow = lambda user_id: True
    return instance


@pytest.mark.asyncio
async def test_the_worker_sends_what_the_brain_returns(worker):
    with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
         patch("src.worker.meta") as sender:
        brain.return_value = "*Micro Finance Scheme*\n6% interest"
        sender.send_text = AsyncMock(return_value=True)

        await worker._process_message(
            {"from_number": "user1", "body": "pension", "message_sid": "m1"}, 1,
        )

        brain.assert_awaited_once_with("user1", "pension")
        sender.send_text.assert_awaited_once_with(
            to="user1", body="*Micro Finance Scheme*\n6% interest",
        )


@pytest.mark.asyncio
async def test_an_opted_out_person_is_sent_nothing(worker):
    """The brain returns "" for someone who sent STOP. Sending them a message
    saying they will get no messages would defeat the entire point."""
    with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
         patch("src.worker.meta") as sender:
        brain.return_value = ""
        sender.send_text = AsyncMock(return_value=True)

        await worker._process_message(
            {"from_number": "user1", "body": "anything", "message_sid": "m2"}, 1,
        )

        sender.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failure_still_gets_a_reply(worker):
    """An exception must not leave someone staring at a message that never gets
    an answer — from their side that is indistinguishable from being ignored."""
    with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
         patch("src.worker.meta") as sender:
        brain.side_effect = RuntimeError("corpus is being rebuilt")
        sender.send_text = AsyncMock(return_value=True)

        await worker._process_message(
            {"from_number": "user1", "body": "hello", "message_sid": "m3"}, 1,
        )

        sender.send_text.assert_awaited_once()
        body = sender.send_text.await_args.kwargs["body"]
        assert "again" in body.lower()
        assert "lost" in body.lower()


@pytest.mark.asyncio
async def test_a_voice_note_is_transcribed_before_it_reaches_the_brain(worker):
    """The brain should never need to know how the words arrived."""
    with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
         patch("src.worker.meta") as sender, \
         patch("src.worker.speech") as speech, \
         patch("src.worker.speech") as speech:
        speech.is_available.return_value = True
        sender.fetch_media = AsyncMock(return_value=(b"audio-bytes", "audio/ogg"))
        speech.transcribe = AsyncMock(return_value=Transcript(
            text="मुझे पेंशन चाहिए", ok=True, language="hi", provider="sarvam",
        ))
        brain.return_value = "reply"
        sender.send_text = AsyncMock(return_value=True)

        await worker._process_message(
            {"from_number": "user1", "body": "", "message_sid": "m4",
             "media_id": "MEDIA1",
             "media_type": "audio/ogg"}, 1,
        )

        brain.assert_awaited_once_with("user1", "मुझे पेंशन चाहिए")


@pytest.mark.asyncio
async def test_an_unintelligible_voice_note_asks_for_another(worker):
    """Silence would read as the message never arriving."""
    with patch("src.worker.brain_reply", new_callable=AsyncMock) as brain, \
         patch("src.worker.meta") as sender, \
         patch("src.worker.speech") as speech, \
         patch("src.worker.speech") as speech:
        speech.is_available.return_value = True
        sender.fetch_media = AsyncMock(return_value=(b"noise", "audio/ogg"))
        speech.transcribe = AsyncMock(return_value=Transcript(unclear=True))
        sender.send_text = AsyncMock(return_value=True)

        await worker._process_message(
            {"from_number": "user1", "body": "", "message_sid": "m5",
             "media_id": "MEDIA1"}, 1,
        )

        brain.assert_not_awaited()
        assert "voice note" in sender.send_text.await_args.kwargs["body"].lower()
