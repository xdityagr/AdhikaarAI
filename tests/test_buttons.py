"""Button-payload parsing in the legacy intake graph.

The worker no longer uses this graph — see tests/test_whatsapp_worker.py
for what WhatsApp actually does now. These stay because src/graph.py
still exists and its parsing is still correct.
"""

import pytest
from unittest.mock import AsyncMock, patch
from src.graph import build_graph, ConversationState
from src.config import get_settings
import asyncio


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def graph():
    return build_graph().compile()


@pytest.mark.asyncio
async def test_button_payload_parsing_project_type(graph, settings):
    # Test valid button payload for project type
    result = await graph.ainvoke(
        {
            "message": "some ignored text", 
            "button_payload": "project_type:business",
            "consent_given": True,
            "intake_step": "awaiting_project_type"
        },
        config={"configurable": {"thread_id": "123"}}
    )
    assert result["project_type"] == "business"
    assert result["intake_step"] == "awaiting_cost"
    assert result["button_payload"] == ""


@pytest.mark.asyncio
async def test_button_payload_parsing_gender(graph, settings):
    # Test valid button payload for gender
    result = await graph.ainvoke(
        {
            "message": "ignored",
            "button_payload": "gender:female",
            "project_type": "education",
            "project_cost": 200000,
            "annual_income": 100000,
            "intake_step": "awaiting_gender",
            "consent_given": True
        },
        config={"configurable": {"thread_id": "124"}}
    )
    assert result["gender"] == "female"
    assert result["intake_step"] == "done"
    assert result["button_payload"] == ""


@pytest.mark.asyncio
async def test_fallback_to_text_parsing_project_type(graph, settings):
    # Test fallback to text parsing when button payload is missing/invalid
    result = await graph.ainvoke(
        {
            "message": "I want to start a business", 
            "button_payload": "", 
            "intake_step": "awaiting_project_type",
            "consent_given": True
        },
        config={"configurable": {"thread_id": "125"}}
    )
    assert result["project_type"] == "business"
    assert result["intake_step"] == "awaiting_cost"
    
    # Test invalid payload fallback
    result = await graph.ainvoke(
        {
            "message": "I want to start a business", 
            "button_payload": "invalid:payload", 
            "intake_step": "awaiting_project_type",
            "consent_given": True
        },
        config={"configurable": {"thread_id": "126"}}
    )
    assert result["project_type"] == "business"
    assert result["intake_step"] == "awaiting_cost"
