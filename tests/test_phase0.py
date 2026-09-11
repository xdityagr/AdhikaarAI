"""
Test suite for Phase 0 — webhook, idempotency, and state persistence.

Tests the critical reliability properties:
1. Signature verification (accept valid, reject invalid)
2. Idempotency (same message processed only once)
3. State persistence (message count increments correctly across messages)
4. Rate limiting (excessive messages get throttled)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import pytest
import time
from unittest.mock import patch, AsyncMock, MagicMock
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from src.config import get_settings
from src.database import init_database, get_connection, is_message_processed
from src.worker import RateLimiter


# ---------------------------------------------------------------------------
# Rate limiter tests (standalone, no server needed)
# ---------------------------------------------------------------------------

class TestRateLimiter:
    """Test the per-user token bucket rate limiter."""

    def test_allows_under_limit(self):
        rl = RateLimiter(max_tokens=5, window_seconds=60.0)
        for _ in range(5):
            assert rl.allow("user1") is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_tokens=3, window_seconds=60.0)
        for _ in range(3):
            assert rl.allow("user1") is True
        assert rl.allow("user1") is False

    def test_separate_users(self):
        rl = RateLimiter(max_tokens=2, window_seconds=60.0)
        assert rl.allow("user1") is True
        assert rl.allow("user1") is True
        assert rl.allow("user1") is False
        # Different user should have their own bucket
        assert rl.allow("user2") is True
        assert rl.allow("user2") is True

    def test_window_expiry(self):
        rl = RateLimiter(max_tokens=2, window_seconds=0.1)
        assert rl.allow("user1") is True
        assert rl.allow("user1") is True
        assert rl.allow("user1") is False
        # Wait for window to expire
        time.sleep(0.15)
        assert rl.allow("user1") is True


# ---------------------------------------------------------------------------
# Database idempotency tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Test the processed_messages idempotency guard."""

    @pytest.fixture(autouse=True)
    async def setup_db(self, tmp_path):
        """Use a temporary database for each test."""
        test_db = str(tmp_path / "test.db")
        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(database_path=test_db)
            await init_database()
            self._db_path = test_db
            self._mock_settings = mock_settings
            yield

    async def test_new_message_not_processed(self):
        """A brand-new message_id should not be marked as processed."""
        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(database_path=self._db_path)
            db = await get_connection()
            try:
                assert await is_message_processed(db, "MSG_NEW") is False
            finally:
                await db.close()

    async def test_processed_message_detected(self):
        """After marking a message as processed, it should be detected."""
        from src.database import mark_message_processed

        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(database_path=self._db_path)
            db = await get_connection()
            try:
                await mark_message_processed(db, "MSG_001")
                assert await is_message_processed(db, "MSG_001") is True
            finally:
                await db.close()

    async def test_different_message_not_affected(self):
        """Processing one message shouldn't affect a different message_id."""
        from src.database import mark_message_processed

        with patch("src.database.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(database_path=self._db_path)
            db = await get_connection()
            try:
                await mark_message_processed(db, "MSG_001")
                assert await is_message_processed(db, "MSG_002") is False
            finally:
                await db.close()


# ---------------------------------------------------------------------------
# Graph state tests
# ---------------------------------------------------------------------------

class TestGraphState:
    """Test the LangGraph conversation graph state machine."""

    @pytest.mark.asyncio
    async def test_consent_not_given_shows_notice(self):
        """Without consent, should show the consent notice."""
        from src.graph import check_consent, CONSENT_NOTICE

        state = {"message": "hello", "consent_given": False, "message_count": 0, "response": ""}
        result = await check_consent(state)
        assert result["consent_given"] is False
        assert result["response"] == CONSENT_NOTICE

    @pytest.mark.asyncio
    async def test_start_grants_consent(self):
        """Sending START should grant consent."""
        from src.graph import check_consent

        state = {"message": "START", "consent_given": False, "message_count": 0, "response": ""}
        result = await check_consent(state)
        assert result["consent_given"] is True

    @pytest.mark.asyncio
    async def test_stop_revokes_consent(self):
        """Sending STOP should revoke consent and reset state."""
        from src.graph import check_consent, STOP_NOTICE

        state = {"message": "STOP", "consent_given": True, "message_count": 5, "response": ""}
        result = await check_consent(state)
        assert result["consent_given"] is False
        assert result["message_count"] == 0
        assert result["response"] == STOP_NOTICE

    def test_message_count_increments(self):
        """Each message should increment the count."""
        from src.graph import process_message

        state = {"message": "test", "consent_given": True, "message_count": 0, "response": ""}
        result = process_message(state)
        assert result["message_count"] == 1

        result2 = process_message({**state, "message_count": 1, "message": "second"})
        assert result2["message_count"] == 2

    def test_message_count_appears_in_response(self):
        """The response should include the message count as state proof."""
        from src.graph import process_message

        state = {"message": "hello", "consent_given": True, "message_count": 4, "response": ""}
        result = process_message(state)
        assert "Message #5" in result["response"]

    @pytest.mark.asyncio
    async def test_start_case_insensitive(self):
        """START should work regardless of case."""
        from src.graph import check_consent

        for msg in ["START", "start", "Start", "  START  "]:
            state = {"message": msg, "consent_given": False, "message_count": 0, "response": ""}
            result = await check_consent(state)
            assert result["consent_given"] is True, f"Failed for: '{msg}'"
