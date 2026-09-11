"""
Caching module (Phase 3).

Handles the `recommendation_cache` SQLite table.
Crucially, fingerprints are generated based on the OUTCOMES of Tier 1 (scheme matches),
not the continuous raw inputs (income, cost) of the user profile. This guarantees a high
cache hit rate for generation since the same scheme match outcomes across different users
will reuse the same LLM-translated template.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
import aiosqlite

from src.schemes import SchemeMatch

logger = logging.getLogger(__name__)


def generate_fingerprint(matches: list[SchemeMatch]) -> str:
    """
    Creates a SHA-256 hash of the matched outcomes.
    Includes scheme_id and women_rebate_pct.
    Does NOT include user's specific income or project cost.
    """
    if not matches:
        # Special fingerprint for "no match"
        data = "NO_MATCH"
    else:
        # Build deterministic string of matches
        parts = []
        for match in matches:
            parts.append(f"{match.scheme_id}_{match.women_rebate_pct}")
        
        # Sort to prevent cache fragmenting purely on match order
        parts.sort()
        data = "|".join(parts)
        
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def get_cached_template(db: aiosqlite.Connection, fingerprint: str, language: str) -> str | None:
    """
    Fetch the cached response template for this outcome fingerprint + language.
    """
    try:
        cursor = await db.execute(
            "SELECT explanation FROM recommendation_cache WHERE profile_fingerprint = ? AND language = ?",
            (fingerprint, language)
        )
        row = await cursor.fetchone()
        if row:
            return row["explanation"]
        return None
    except Exception as e:
        logger.error(f"Failed to read cache: {e}")
        return None


async def set_cached_template(
    db: aiosqlite.Connection, 
    fingerprint: str, 
    language: str, 
    scheme_id: str, 
    template: str
) -> None:
    """
    Save the newly generated response template to the cache.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.execute(
            """
            INSERT OR IGNORE INTO recommendation_cache 
            (profile_fingerprint, language, scheme_id, explanation, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fingerprint, language, scheme_id, template, now)
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to write cache: {e}")

