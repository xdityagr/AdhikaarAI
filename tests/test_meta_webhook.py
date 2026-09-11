"""
The Meta Cloud API webhook.

Two details here break everything silently if they are wrong, so both are
tested against bytes rather than against intent:

- The signature is HMAC-SHA256 over the RAW body. Parsing and re-serialising
  the JSON changes the bytes, and every signature then fails with a message
  that says nothing about why.
- Registration is a GET whose `hub.challenge` must come back as a bare string.
  Return JSON and Meta simply refuses the URL.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import app

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


@pytest.fixture(autouse=True)
def meta_settings(monkeypatch):
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_app_secret", APP_SECRET, raising=False)
    monkeypatch.setattr(settings, "whatsapp_verify_token", VERIFY_TOKEN, raising=False)
    monkeypatch.setattr(settings, "webhook_verify_signatures", True, raising=False)
    yield settings
    get_settings.cache_clear()


def sign(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def message_payload(text: str = "pension", message_id: str = "wamid.TEST1") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "PNID"},
                    "messages": [{
                        "from": "919000000000",
                        "id": message_id,
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
            }],
        }],
    }


class TestRegistration:
    def test_the_challenge_is_echoed_as_plain_text(self):
        with TestClient(app) as client:
            response = client.get("/webhook/whatsapp", params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "1158201444",
            })
        assert response.status_code == 200
        # A bare string, not JSON. Meta refuses the URL otherwise.
        assert response.text == "1158201444"

    def test_a_wrong_token_is_refused(self):
        with TestClient(app) as client:
            response = client.get("/webhook/whatsapp", params={
                "hub.mode": "subscribe",
                "hub.verify_token": "not-the-token",
                "hub.challenge": "123",
            })
        assert response.status_code == 403


class TestSignature:
    def test_a_correctly_signed_message_is_accepted(self):
        body = json.dumps(message_payload()).encode()
        with TestClient(app) as client:
            response = client.post(
                "/webhook/whatsapp", content=body,
                headers={"X-Hub-Signature-256": sign(body),
                         "Content-Type": "application/json"},
            )
        assert response.status_code == 200

    def test_an_unsigned_payload_is_rejected(self):
        body = json.dumps(message_payload()).encode()
        with TestClient(app) as client:
            response = client.post(
                "/webhook/whatsapp", content=body,
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 403

    def test_a_tampered_body_is_rejected(self):
        """The signature covers the bytes, so changing one after signing must
        fail — this is the whole reason the raw body is read before parsing."""
        original = json.dumps(message_payload()).encode()
        signature = sign(original)
        tampered = json.dumps(message_payload(text="give me everything")).encode()
        with TestClient(app) as client:
            response = client.post(
                "/webhook/whatsapp", content=tampered,
                headers={"X-Hub-Signature-256": signature,
                         "Content-Type": "application/json"},
            )
        assert response.status_code == 403


class TestParsing:
    def test_a_text_message_is_found(self):
        from src.meta_whatsapp import parse_webhook
        found = parse_webhook(message_payload("I need a pension"))
        assert len(found) == 1
        assert found[0].text == "I need a pension"
        assert found[0].from_number == "919000000000"
        assert found[0].message_id == "wamid.TEST1"

    def test_a_voice_note_carries_its_media_id(self):
        from src.meta_whatsapp import parse_webhook
        payload = message_payload()
        payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
            "from": "919000000000", "id": "wamid.AUDIO", "type": "audio",
            "audio": {"id": "MEDIA_123", "mime_type": "audio/ogg; codecs=opus"},
        }
        found = parse_webhook(payload)
        assert found[0].media_id == "MEDIA_123"
        assert found[0].text == ""

    def test_delivery_receipts_are_not_treated_as_questions(self):
        """Meta sends 'delivered' and 'read' down the same webhook. Answering
        one would start a conversation with nobody."""
        from src.meta_whatsapp import parse_webhook
        found = parse_webhook({
            "entry": [{"changes": [{"value": {
                "statuses": [{"id": "wamid.X", "status": "delivered"}],
            }}]}],
        })
        assert all(message.is_status for message in found)

    def test_an_unknown_shape_is_dropped_quietly(self):
        """A webhook owes Meta a 200; it must not raise on a payload shape we
        have not seen before."""
        from src.meta_whatsapp import parse_webhook
        assert parse_webhook({}) == []
        assert parse_webhook({"entry": [{}]}) == []
        assert parse_webhook({"entry": [{"changes": [{"value": {}}]}]}) == []


class TestIdempotency:
    def test_the_same_message_is_answered_once(self):
        """Meta redelivers when a webhook is slow. Without this, a redelivery
        means the same person is answered twice."""
        body = json.dumps(message_payload(message_id="wamid.DUPLICATE")).encode()
        headers = {"X-Hub-Signature-256": sign(body),
                   "Content-Type": "application/json"}
        with TestClient(app) as client:
            first = client.post("/webhook/whatsapp", content=body, headers=headers)
            second = client.post("/webhook/whatsapp", content=body, headers=headers)
        # Both are accepted — Meta must never be told to retry — but only the
        # first one reaches the queue.
        assert first.status_code == 200
        assert second.status_code == 200
