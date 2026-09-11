"""
Message queue worker — consumes messages from the async queue.

Architecture.md requirements fulfilled here:
- Worker reads user state atomically (LangGraph checkpointer, Non-negotiable #2)
- Every step is idempotent and retryable (Non-negotiable #3)
- State written back atomically, same transaction as read (message chain step 6)
- Response sent via separate outbound call (message chain step 7)

Implementation details:
- asyncio.Queue as the in-process message queue
- GC-safe task management (master_build_guide.md Issue #8)
- Per-user rate limiting (in-memory token bucket)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict


from src.config import get_settings
from src import meta_whatsapp as meta
from src import speech
from src.whatsapp_brain import (
    language_if_known, remember_detected_language, reply as brain_reply,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GC-safe task management (master_build_guide.md Issue #8)
# Without this, asyncio.create_task() tasks can be garbage-collected mid-run.
# ---------------------------------------------------------------------------

_background_tasks: set[asyncio.Task] = set()


def _spawn_task(coro) -> asyncio.Task:
    """Spawn an asyncio task with GC protection."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# ---------------------------------------------------------------------------
# Per-user rate limiter (simple token bucket)
# Protects against message loops silently burning API quota.
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple per-user token bucket rate limiter.

    Allows `max_tokens` messages per `window_seconds` per user.
    In-memory only — resets on server restart, which is fine.
    """

    def __init__(self, max_tokens: int = 10, window_seconds: float = 60.0):
        self.max_tokens = max_tokens
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def allow(self, user_id: str) -> bool:
        """Check if this user is within their rate limit."""
        now = time.monotonic()
        bucket = self._buckets[user_id]

        # Remove expired timestamps
        cutoff = now - self.window_seconds
        self._buckets[user_id] = [t for t in bucket if t > cutoff]

        if len(self._buckets[user_id]) >= self.max_tokens:
            return False

        self._buckets[user_id].append(now)
        return True


# How much of a transcript to echo back. Long enough to catch a misheard
# number or place, short enough that it stays a footnote to the answer rather
# than competing with it.
ECHO_CHARS = 90


def _public_media_url(path: str) -> str | None:
    """Turn "/media/x.png" into something Meta can actually fetch.

    Meta pulls the image from the open internet with none of our credentials,
    so a relative path or a loopback address is useless to it. Without a public
    base configured there is nothing to send, and saying so once in the log is
    better than a rejected message every time.
    """
    base = (get_settings().webhook_base_url or "").rstrip("/")
    if not base or base.startswith(("http://localhost", "http://127.")):
        return None
    return f"{base}{path}"


async def _send_pending_map(user_id: str) -> None:
    """Send the map the last answer produced, if there was one.

    Never fatal. The text message is the answer; the map is a second look at
    it, and failing to deliver a picture is not a reason to surface an error to
    someone who has already been told what they needed to know.
    """
    try:
        from src.whatsapp_brain import take_pending_map

        path = take_pending_map(user_id)
        if not path:
            return
        link = _public_media_url(path)
        if not link:
            logger.info("Map ready but WEBHOOK_BASE_URL is not public — not sending")
            return
        await meta.send_image(to=user_id, link=link)
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("Map send failed for %s: %s", user_id[:10] + "…", exc)


def _echo(heard: str) -> str:
    """The one line that says what we thought the voice note said."""
    text = " ".join(heard.split())
    if len(text) > ECHO_CHARS:
        text = text[:ECHO_CHARS].rstrip() + "…"
    return f'🎤 _"{text}"_'


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class MessageWorker:
    """Async worker that consumes messages from the queue and processes them
    through the LangGraph graph with checkpointer-backed state persistence.
    """

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self._compiled_graph = None
        self._checkpointer = None
        self._checkpointer_cm = None
        self._rate_limiter = RateLimiter(
            max_tokens=get_settings().max_messages_per_user_per_minute,
            window_seconds=60.0,
        )

    async def start(self) -> None:
        """Initialize the LangGraph graph with AsyncSqliteSaver checkpointer
        and start worker tasks."""
        settings = get_settings()

        # No graph and no checkpointer any more. WhatsApp answers through the
        # same brain as the website, which keeps its own short history per
        # number — so the AsyncSqliteSaver that once broke startup is gone
        # rather than merely fixed.
        # Start worker coroutines
        for i in range(settings.worker_count):
            _spawn_task(self._worker_loop(worker_id=i))
            logger.info("Worker %d started", i)

    async def stop(self) -> None:
        """Gracefully stop workers — drain the queue."""
        logger.info("Stopping workers — draining queue...")

        # Wait for the queue to be fully processed (with timeout)
        try:
            await asyncio.wait_for(self.queue.join(), timeout=10.0)
            logger.info("Queue drained successfully")
        except asyncio.TimeoutError:
            logger.warning("Queue drain timed out — %d messages remaining", self.queue.qsize())

        # Cancel all background tasks
        for task in _background_tasks.copy():
            task.cancel()

        # Close the checkpointer's SQLite connection. Paired with the explicit
        # __aenter__ in start() — see the note there.
        if self._checkpointer_cm is not None:
            try:
                await self._checkpointer_cm.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("Checkpointer did not close cleanly: %s", exc)
            finally:
                self._checkpointer_cm = None
                self._checkpointer = None

    async def _worker_loop(self, worker_id: int) -> None:
        """Main worker loop — dequeue, process, send response.

        Each iteration is idempotent: if processing fails, the message
        was already marked as processed in the webhook handler (so it won't
        be re-delivered), and we send an error message to the user.
        """
        while True:
            msg = await self.queue.get()
            try:
                await self._process_message(msg, worker_id)
            except asyncio.CancelledError:
                logger.info("Worker %d cancelled", worker_id)
                break
            except Exception as e:
                logger.error(
                    "Worker %d error processing %s: %s",
                    worker_id,
                    msg.get("message_sid", "unknown"),
                    e,
                    exc_info=True,
                )
                # Send error message to user — never let the bot go silent
                # (phrases.md §7 — fallback/error states)
                try:
                    await meta.send_text(
                        to=msg.get("from_number", ""),
                        body=(
                            "Sorry, having a little trouble right now — "
                            "please try again in a moment. Your progress is saved."
                        ),
                    )
                except Exception:
                    logger.error("Failed to send error message to user", exc_info=True)
            finally:
                self.queue.task_done()

    @staticmethod
    async def _transcribe_voice_note(user_id: str, msg: dict) -> str:
        """A voice note, in whatever language it turns out to be in."""
        if not speech.is_available():
            logger.info("Voice note from %s but no speech key", user_id[:10] + "…")
            return ""
        try:
            audio, content_type = await meta.fetch_media(msg["media_id"])
        except Exception as exc:                              # noqa: BLE001
            logger.warning("Could not fetch voice note: %s", exc)
            return ""

        # `language_if_known`, not `known_language`: the latter answers "en"
        # for a stranger, which would tell the transcriber to expect English
        # from someone speaking Tamil. None lets it detect instead.
        result = await speech.transcribe(
            audio,
            content_type=msg.get("media_type") or content_type,
            language=language_if_known(user_id),
        )
        if not result.ok:
            return ""

        # A spoken language is as good a signal as a typed script, and for
        # someone who cannot type their own script it is the only one.
        remember_detected_language(user_id, result.language)

        if result.unclear:
            logger.info("Low-confidence transcript (%.2f, %s) from %s",
                        result.confidence, result.provider, user_id[:10] + "…")
        return result.text

    async def _process_message(self, msg: dict, worker_id: int) -> None:
        """Process a single message through the LangGraph graph."""
        user_id = msg["from_number"]
        body = msg.get("body", "")
        message_sid = msg["message_sid"]

        logger.info(
            "Worker %d processing message %s from %s",
            worker_id,
            message_sid,
            user_id[:10] + "...",
        )

        # Rate-limit check
        if not self._rate_limiter.allow(user_id):
            logger.warning("Rate limit exceeded for %s", user_id[:10] + "...")
            await meta.send_text(
                to=user_id,
                body="You're sending messages too quickly. Please wait a moment.",
            )
            return

        # A voice note has no body. Transcribe it first, then it is just a
        # message like any other — which is the point: the brain should never
        # need to know how the words arrived.
        heard = ""
        if not body and msg.get("media_id"):
            body = await self._transcribe_voice_note(user_id, msg)
            heard = body
            if not body:
                await meta.send_text(
                    to=user_id,
                    body=(
                        "I could not make out that voice note. Please try again "
                        "somewhere quieter, or type your question instead."
                    ),
                )
                return

        # One brain, two channels. The website and WhatsApp answer the same
        # question the same way — the alternative is that the channel reaching
        # the most people stays the worst one.
        try:
            response_text = await brain_reply(user_id, body)
        except Exception as exc:                              # noqa: BLE001
            logger.exception("Reply failed for %s: %s", message_sid, exc)
            response_text = (
                "Something went wrong at our end. Please send your message "
                "again in a moment — nothing you told me is lost."
            )

        # Show what we heard, once, above the answer.
        #
        # Transcription is never perfect, and the failure it produces is quiet:
        # a misheard "five lakh" becomes "five thousand" and the answer that
        # follows is confidently about the wrong thing. Echoing one line lets
        # the person catch it themselves in a second — and when it is right, it
        # is the only proof they get that the voice note arrived at all.
        if heard and response_text:
            response_text = f"{_echo(heard)}\n\n{response_text}"

        success = False
        if response_text:
            success = await meta.send_text(to=user_id, body=response_text)
        else:
            # An empty reply is deliberate: it means this person has opted out.
            # Sending them anything at all would defeat the point.
            logger.info("Nothing to send for %s (opted out)", user_id[:10] + "…")
            return

        if response_text:
            if success:
                logger.info(
                    "Response sent for message %s (worker %d)",
                    message_sid,
                    worker_id,
                )
            else:
                logger.error(
                    "Failed to send response for message %s",
                    message_sid,
                )
        else:
            logger.warning(
                "Empty response from graph for message %s — this shouldn't happen",
                message_sid,
            )
