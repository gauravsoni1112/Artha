"""
Unit tests for agent router — HTTP-level tests with mocked LLM and DB.

All DB interactions are mocked. No Docker required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest


OWNER_ID = str(uuid.uuid4())
SESSION_ID = str(uuid.uuid4())


@pytest.fixture
def mock_agent_result():
    """Mock successful agent response."""
    return {
        "response": "You spent ₹5,000 on groceries last month.",
        "tool_calls": ["transaction_query"],
        "messages": [
            {"type": "human", "content": "[owner_id=test] What did I spend?"},
            {"type": "ai", "content": "You spent ₹5,000."},
        ],
        "session_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
    }


@pytest.mark.asyncio
async def test_chat_returns_200(async_client, mock_agent_result):
    """Happy path: POST /agent/chat returns 200 with correct structure."""
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=mock_agent_result)

        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "How much did I spend on groceries?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "You spent ₹5,000 on groceries last month."
    assert data["tool_calls"] == ["transaction_query"]
    assert "session_id" in data
    assert "run_id" in data


@pytest.mark.asyncio
async def test_chat_validates_owner_id_uuid(async_client):
    """Malformed owner_id returns 422 Unprocessable Entity."""
    resp = await async_client.post(
        "/agent/chat",
        json={"owner_id": "not-a-uuid", "message": "Hello"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_empty_message(async_client):
    """Empty message fails Pydantic validation."""
    resp = await async_client.post(
        "/agent/chat",
        json={"owner_id": OWNER_ID, "message": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_message_over_2000_chars(async_client):
    """Message > 2000 chars rejected."""
    resp = await async_client.post(
        "/agent/chat",
        json={"owner_id": OWNER_ID, "message": "x" * 2001},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_llm_failure_returns_500(async_client):
    """LLM errors are caught and return 500."""
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(
            side_effect=RuntimeError("LLM API timeout")
        )

        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "Hello"},
        )

    assert resp.status_code == 500
    assert "Agent error" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_chat_with_session_id(async_client, mock_agent_result):
    """Session ID is passed to agent and returned in response."""
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=mock_agent_result)

        resp = await async_client.post(
            "/agent/chat",
            json={
                "owner_id": OWNER_ID,
                "message": "Follow-up question",
                "session_id": SESSION_ID,
            },
        )

    assert resp.status_code == 200
    # Verify agent.chat was called with session_id
    MockAgent.return_value.chat.assert_called_once()
    call_kwargs = MockAgent.return_value.chat.call_args[1]
    assert call_kwargs["session_id"] == SESSION_ID


@pytest.mark.asyncio
async def test_chat_tool_calls_returned(async_client):
    """Tool calls from agent are included in response."""
    result_with_multiple_tools = {
        "response": "Here's your data...",
        "tool_calls": ["transaction_query", "category_analysis", "net_worth"],
        "messages": [],
        "session_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
    }

    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=result_with_multiple_tools)

        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "Full financial summary?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tool_calls"]) == 3
    assert "transaction_query" in data["tool_calls"]
    assert "category_analysis" in data["tool_calls"]
    assert "net_worth" in data["tool_calls"]


@pytest.mark.asyncio
async def test_chat_request_validation_missing_owner_id(async_client):
    """Missing owner_id returns 422."""
    resp = await async_client.post(
        "/agent/chat",
        json={"message": "What's my balance?"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_request_validation_missing_message(async_client):
    """Missing message returns 422."""
    resp = await async_client.post(
        "/agent/chat",
        json={"owner_id": OWNER_ID},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_response_includes_all_fields(async_client, mock_agent_result):
    """Response schema includes all required fields."""
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=mock_agent_result)

        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "Test"},
        )

    assert resp.status_code == 200
    data = resp.json()
    required_fields = ["owner_id", "message", "response", "tool_calls", "session_id", "run_id"]
    for field in required_fields:
        assert field in data


@pytest.mark.asyncio
async def test_chat_owner_id_in_response_matches_request(async_client, mock_agent_result):
    """Response owner_id matches request owner_id."""
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=mock_agent_result)

        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "Test"},
        )

    assert resp.status_code == 200
    assert resp.json()["owner_id"] == OWNER_ID


@pytest.mark.asyncio
async def test_chat_message_in_response_matches_request(async_client, mock_agent_result):
    """Response message echoes the request message."""
    test_message = "What is my net worth?"

    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=mock_agent_result)

        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": test_message},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == test_message
