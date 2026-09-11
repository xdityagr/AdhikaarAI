import pytest
import aiosqlite
from pathlib import Path

from src.cache import generate_fingerprint, get_cached_template, set_cached_template
from src.schemes import SchemeMatch
from src.database import init_database, get_connection
from src.config import get_settings


@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path):
    settings = get_settings()
    # Point db to a temporary file
    db_file = tmp_path / "test.db"
    settings.database_path = str(db_file)
    
    await init_database()
    yield
    if db_file.exists():
        db_file.unlink()


def test_fingerprint_consistency():
    # User 1: 5L income, 1L cost
    matches_user1 = [
        SchemeMatch(
            scheme_id="MICRO_FINANCE",
            name="Micro Finance",
            why_eligible="Matched.",
            rate_min=6.5,
            rate_max=8.0,
            max_project_cost=140000,
            financing_pct=0.90,
            women_rebate_pct=0.0
        )
    ]
    
    # User 2: 2L income, 50k cost
    matches_user2 = [
        SchemeMatch(
            scheme_id="MICRO_FINANCE",
            name="Micro Finance",
            why_eligible="Matched for different reasons.",
            rate_min=6.5,
            rate_max=8.0,
            max_project_cost=140000,
            financing_pct=0.90,
            women_rebate_pct=0.0
        )
    ]

    fp1 = generate_fingerprint(matches_user1)
    fp2 = generate_fingerprint(matches_user2)

    # Different users who match the same scheme MUST have the exact same fingerprint
    assert fp1 == fp2

    # A female applicant gets the rebate, outcome is different
    matches_user3 = [
        SchemeMatch(
            scheme_id="MICRO_FINANCE",
            name="Micro Finance",
            why_eligible="Matched.",
            rate_min=6.5,
            rate_max=8.0,
            max_project_cost=140000,
            financing_pct=0.90,
            women_rebate_pct=0.5
        )
    ]
    fp3 = generate_fingerprint(matches_user3)
    assert fp3 != fp1

    # Empty match case
    fp_no_match = generate_fingerprint([])
    assert isinstance(fp_no_match, str)


@pytest.mark.asyncio
async def test_cache_set_and_get():
    matches = [
        SchemeMatch(
            scheme_id="TERM_LOAN",
            name="Term Loan",
            why_eligible="Match",
            rate_min=6.5,
            rate_max=15.0,
            max_project_cost=5000000,
            financing_pct=0.90,
        )
    ]
    fingerprint = generate_fingerprint(matches)
    language = "en"
    template = "This is a cached {project_cost} template for {rate}%."
    
    db = await get_connection()
    try:
        # Cache should be empty initially
        cached = await get_cached_template(db, fingerprint, language)
        assert cached is None
        
        # Set cache
        await set_cached_template(db, fingerprint, language, "TERM_LOAN", template)
        
        # Cache should now hit
        cached_again = await get_cached_template(db, fingerprint, language)
        assert cached_again == template
    finally:
        await db.close()
