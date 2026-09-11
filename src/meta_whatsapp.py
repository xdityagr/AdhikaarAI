"""
WhatsApp through Meta's Cloud API, with nobody in between.

Replaces Twilio. One less party between a person's message and the answer, one
less bill, and no sandbox number that recipients must first text a join code to.

Almost nothing about this is the same as Twilio, which is why it is a separate
module rather than a flag:

- Twilio signs with HMAC-SHA1 over the URL and sorted form fields, keyed on the
  auth token. Meta signs with HMAC-SHA256 over the raw request body, keyed on
  the App Secret, in an `X-Hub-Signature-256` header. The bytes must be the
  ones that arrived — re-serialising the parsed JSON changes them and every
  signature fails.
- Twilio posts form fields. Meta posts JSON nested four levels deep, and sends
  delivery receipts through the same webhook as real messages.
- Twilio's media URLs take basic auth. Meta's take two requests: ask for the
  media's URL by id, then fetch it with a Bearer token.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from src.paths import strip_media_paths

from src.config import get_settings

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.whatsapp_token and settings.whatsapp_phone_number_id)


def _base() -> str:
    settings = get_settings()
    return f"{GRAPH}/{settings.whatsapp_api_version}"


# ---------------------------------------------------------------------------
# Incoming
# ---------------------------------------------------------------------------

@dataclass
class IncomingMessage:
    message_id: str
    from_number: str
    text: str = ""
    media_id: str = ""
    media_type: str = ""
    """Meta sends delivery receipts down the same pipe; those are not messages."""
    is_status: bool = False


def verify_signature(raw_body: bytes, header: Optional[str]) -> bool:
    """Check `X-Hub-Signature-256` against the raw bytes Meta sent.

    Uses `compare_digest`, because comparing HMACs with `==` leaks how much of
    the digest matched through timing — the whole point of signing is lost if
    the check itself is exploitable.
    """
    settings = get_settings()

    if not settings.webhook_verify_signatures:
        logger.warning("Signature verification DISABLED — local testing only")
        return True

    if not settings.whatsapp_app_secret:
        logger.error("No WHATSAPP_APP_SECRET set — refusing to accept webhooks")
        return False

    if not header or not header.startswith("sha256="):
        logger.warning("Missing or malformed X-Hub-Signature-256")
        return False

    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_webhook(payload: dict[str, Any]) -> list[IncomingMessage]:
    """Pull the messages out of Meta's nesting.

    The shape is entry[] → changes[] → value → messages[], and `value` may
    instead carry `statuses` (delivered, read) which must be ignored rather
    than answered. Everything is defensive: a payload shape we do not recognise
    should be dropped quietly, not raise inside a webhook that owes Meta a 200.
    """
    found: list[IncomingMessage] = []

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}

            if value.get("statuses"):
                found.append(IncomingMessage(
                    message_id="", from_number="", is_status=True,
                ))
                continue

            for message in value.get("messages", []) or []:
                kind = message.get("type")
                parsed = IncomingMessage(
                    message_id=message.get("id", ""),
                    from_number=message.get("from", ""),
                )

                if kind == "text":
                    parsed.text = (message.get("text") or {}).get("body", "")
                elif kind in ("audio", "voice"):
                    media = message.get(kind) or {}
                    parsed.media_id = media.get("id", "")
                    parsed.media_type = media.get("mime_type", "audio/ogg")
                elif kind == "interactive":
                    # Button and list replies, when we start using them.
                    interactive = message.get("interactive") or {}
                    reply = (
                        interactive.get("button_reply")
                        or interactive.get("list_reply")
                        or {}
                    )
                    parsed.text = reply.get("title") or reply.get("id") or ""
                elif kind == "button":
                    parsed.text = (message.get("button") or {}).get("text", "")
                else:
                    # An image, a document, a location. Nothing to answer yet,
                    # but the message id still matters for idempotency.
                    parsed.text = ""

                if parsed.message_id and parsed.from_number:
                    found.append(parsed)

    return found


# ---------------------------------------------------------------------------
# Outgoing
# ---------------------------------------------------------------------------

async def send_text(to: str, body: str) -> bool:
    """Send one message. Returns whether Meta accepted it."""
    # The last gate. A map is delivered as a picture by `send_image`, so a
    # /media/ path in a text body is always plumbing that escaped — from a
    # renderer, or from the model quoting back something it was shown. Both
    # reply builders already strip it; this is the one place nothing routes
    # around, and it costs a regex on a message we are about to spend a
    # network call on anyway.
    body = strip_media_paths(body)
    settings = get_settings()
    if not is_configured():
        logger.error("WhatsApp not configured — cannot send to %s", to[:8] + "…")
        return False

    url = f"{_base()}/{settings.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        # Link previews turn a scheme URL into a large card that pushes the
        # answer off the screen on a small phone.
        "text": {"preview_url": False, "body": body},
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            )
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("Send failed to %s: %s", to[:8] + "…", exc)
        return False

    if response.status_code >= 400:
        # Meta's errors are specific and worth reading in full: an expired
        # token, an unregistered number and a 24-hour-window violation all
        # look identical from the outside otherwise.
        logger.warning("Meta rejected the message (%s): %s",
                       response.status_code, response.text[:400])
        return False
    return True


async def send_image(to: str, link: str, caption: str = "") -> bool:
    """Send one image by public URL. Returns whether Meta accepted it.

    Meta fetches `link` itself, from the public internet, with no credentials
    of ours — so it has to be a URL that is genuinely reachable from outside,
    not a loopback address that only works on the machine that rendered it.
    Callers are responsible for building an absolute one.

    No caption is sent by default, and that is deliberate. A caption here would
    have to be written in the reader's language, and there is no translation
    table on this path; an English line under a map in a Tamil conversation is
    worse than no line at all. The message that precedes the image carries the
    explanation, and the OpenStreetMap credit is drawn into the image itself.
    """
    settings = get_settings()
    if not is_configured():
        logger.error("WhatsApp not configured — cannot send image to %s", to[:8] + "…")
        return False

    url = f"{_base()}/{settings.whatsapp_phone_number_id}/messages"
    image: dict[str, str] = {"link": link}
    if caption:
        image["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "image",
        "image": image,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            )
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("Image send failed to %s: %s", to[:8] + "…", exc)
        return False

    if response.status_code >= 400:
        # The usual cause is a link Meta could not fetch: a private host, a
        # self-signed certificate, or a tunnel that has since closed.
        logger.warning("Meta rejected the image (%s): %s",
                       response.status_code, response.text[:400])
        return False
    return True


async def fetch_media(media_id: str) -> tuple[bytes, str]:
    """Two requests: the media's URL by id, then the bytes themselves.

    Both need the Bearer token — the URL that comes back is not public and
    expires quickly, which is why it is fetched immediately rather than stored.
    """
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        lookup = await client.get(f"{_base()}/{media_id}", headers=headers)
        lookup.raise_for_status()
        info = lookup.json()

        download = await client.get(
            info["url"], headers=headers, follow_redirects=True,
        )
        download.raise_for_status()
        return download.content, info.get("mime_type", "audio/ogg")


async def mark_read(message_id: str) -> None:
    """Show the blue ticks.

    Cosmetic, and worth it: a person who has sent a question into what looks
    like a void will send it again, and the second copy is a wasted model call
    as well as a worried person.
    """
    settings = get_settings()
    if not is_configured():
        return
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            await client.post(
                f"{_base()}/{settings.whatsapp_phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message_id,
                },
                headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            )
    except Exception as exc:                                  # noqa: BLE001
        logger.debug("Could not mark %s read: %s", message_id[:12], exc)
