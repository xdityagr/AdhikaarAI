import pytest
from unittest.mock import AsyncMock, patch

from src.llm import extract_project_type, generate_recommendation_template, format_recommendation
from src.schemes import SchemeMatch, UserProfile
from src.config import get_settings


@pytest.mark.asyncio
async def test_extract_project_type_no_key():
    # If no key is set, should safely return None
    settings = get_settings()
    settings.gemini_api_key = ""
    result = await extract_project_type("I want to open a shop")
    assert result is None


@pytest.mark.asyncio
async def test_extract_project_type_success():
    settings = get_settings()
    settings.gemini_api_key = "fake_key"
    
    with patch("src.llm.ChatGoogleGenerativeAI") as mock_chat:
        from unittest.mock import MagicMock
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance
        
        # Mock structured output
        mock_structured = AsyncMock()
        mock_instance.with_structured_output = MagicMock(return_value=mock_structured)
        
        class FakeResult:
            project_type = "business"
            
        mock_structured.ainvoke.return_value = FakeResult()
        
        result = await extract_project_type("I want to open a tailoring shop")
        assert result == "business"


@pytest.mark.asyncio
async def test_generate_recommendation_template_fallback():
    settings = get_settings()
    settings.gemini_api_key = ""
    
    matches = [
        SchemeMatch(
            scheme_id="TERM_LOAN",
            name="Term Loan",
            why_eligible="Matched.",
            rate_min=6.5,
            rate_max=15.0,
            max_project_cost=5000000,
            financing_pct=0.90,
        )
    ]
    
    template = await generate_recommendation_template(matches, "en")
    assert "Term Loan" in template
    assert "{project_cost}" in template
    assert "{rate}" in template
    assert "{moratorium}" in template


def test_format_recommendation():
    # Verify deterministic formatting does not invent rates and strictly uses Tier 1 math
    template = "Cost is ₹{project_cost}, rate is {rate}%, moratorium {moratorium}."
    
    profile = UserProfile(
        project_type="business",
        project_cost=150000,
        annual_income=100000,
        gender="female"
    )
    
    matches = [
        SchemeMatch(
            scheme_id="TERM_LOAN",
            name="Term Loan",
            why_eligible="Matched.",
            rate_min=6.5,
            rate_max=15.0,  # Max rate is what we show in template substitution for baseline
            max_project_cost=5000000,
            financing_pct=0.90,
            women_rebate_pct=0.5
        )
    ]
    
    result = format_recommendation(template, profile, matches)
    
    # Indian digit grouping: 1,50,000 — not 150,000 (schemes.format_rupees)
    assert "₹1,50,000" in result
    # The intro must quote the SAME rate the EMI is computed at. It used to use
    # rate_max while the calculator used rate_min, so a Term Loan message said
    # "15%" above an EMI calculated at 6.5%. Now: rate_min 6.5 - rebate 0.5 = 6.0.
    assert "6.0%" in result
    assert "14.5%" not in result, "rate_max must not leak into the intro"
    # Settings default is 6
    assert "6" in result
