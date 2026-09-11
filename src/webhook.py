"""
Webhook handler — the most critical module in the system.

It does only this:
  1. Verify the signature
  2. Check idempotency (have we already answered this message?)
  3. Enqueue
  4. Return 200 immediately

No model calls. No slow work. No database writes beyond the idempotency check.
Budget: well under 50ms.

The reason is a failure mode, not a preference. Doing slow work inside the
handler means the platform times out and redelivers the same message — and
without idempotency, redelivery means answering the same person twice, which is
how a helpful bot becomes a nuisance that gets blocked.

This talks to Meta's Cloud API. Two things about it differ from Twilio in ways
that silently break everything if missed:

- The signature is HMAC-SHA256 over the RAW REQUEST BODY, keyed on the App
  Secret. Parsing the JSON and re-serialising it changes the bytes and every
  signature fails, so the raw body is read first and parsed second.
- Registering the webhook is a GET with `hub.challenge`, which must be echoed
  back as a bare string. Meta will not accept the URL otherwise.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request, Response

from src import meta_whatsapp as meta
from src.config import get_settings
from src.database import get_connection, is_message_processed, mark_message_processed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Set by main.py at startup — the queue the workers read from. Module-level to
# avoid a circular import.
_message_queue: asyncio.Queue | None = None


def set_message_queue(queue: asyncio.Queue) -> None:
    """Called by main.py to inject the shared message queue."""
    global _message_queue
    _message_queue = queue


@router.get("/whatsapp")
async def verify_webhook(request: Request) -> Response:
    """Meta's registration handshake.

    It sends `hub.mode=subscribe`, the verify token we chose, and a challenge.
    Echoing the challenge — as plain text, not JSON — is what makes Meta accept
    the URL. Everything else gets a 403, so a wrong token fails loudly here
    rather than mysteriously at the first real message.
    """
    settings = get_settings()
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and token and token == settings.whatsapp_verify_token:
        logger.info("Webhook verified by Meta")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification refused (mode=%s, token matched=%s)",
                   mode, token == settings.whatsapp_verify_token)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_webhook(request: Request) -> Response:
    """Take delivery of messages and get out of the way."""
    # The raw bytes, before anything touches them — the signature is over these.
    raw = await request.body()

    if not meta.verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        logger.warning("Invalid signature — rejecting")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        logger.warning("Webhook body was not JSON")
        return Response(status_code=200)   # Never make Meta retry malformed input

    messages = meta.parse_webhook(payload)
    if not messages:
        return Response(status_code=200)

    if _message_queue is None:
        logger.error("Message queue not initialised — dropping %d message(s)",
                     len(messages))
        return Response(status_code=200)

    db = await get_connection()
    try:
        for message in messages:
            # Delivery receipts arrive down the same pipe. They are not
            # questions and must not be answered.
            if message.is_status:
                continue

            if await is_message_processed(db, message.message_id):
                logger.info("Already answered %s — skipping",
                            message.message_id[:16])
                continue

            # Marked before enqueuing: if the enqueue fails we would rather
            # drop a message than answer it twice.
            await mark_message_processed(db, message.message_id)

            await _message_queue.put({
                "message_sid": message.message_id,
                "from_number": message.from_number,
                "body": message.text.strip(),
                "media_id": message.media_id,
                "media_type": message.media_type,
            })
            logger.info(
                "Queued %s from %s (queue: %d)",
                message.message_id[:16],
                message.from_number[:6] + "…",   # never log a whole number
                _message_queue.qsize(),
            )
    finally:
        await db.close()

    return Response(status_code=200)
