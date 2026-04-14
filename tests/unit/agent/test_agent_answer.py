"""
Unit tests for AgentAnswer schema and the updated /agent/chat router response.

No LLM, no Docker required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.agent.schemas import AgentAnswer


# ── AgentAnswer schema ────────────────────────────────────────────────────────

def test_agent_answer_defaults():
    a = AgentAnswer(answer="You spent ₹5,000.")
    assert a.confidence == 1.0
    assert a.reasoning_steps == []
    assert a.supporting_data == []


def test_agent_answer_confidence_clamped_above_1():
    a = AgentAnswer(answer="ok", confidence=1.5)
    assert a.confidence == 1.0


def test_agent_answer_confidence_clamped_below_0():
    a = AgentAnswer(answer="ok", confidence=-0.5)
    assert a.confidence == 0.0


def test_agent_answer_confidence_invalid_type_defaults_to_1():
    a = AgentAnswer(answer="ok", confidence="bad")  # type: ignore[arg-type]
    assert a.confidence == 1.0


def test_agent_answer_from_agent_result_no_scratchpad():
    a = AgentAnswer.from_agent_result(
        response="Your net worth is ₹10,00,000.",
        scratchpad=None,
        confidence_score=0.9,
    )
    assert a.answer == "Your net worth is ₹10,00,000."
    assert a.confidence == 0.9
    assert a.reasoning_steps == []


def test_agent_answer_from_agent_result_with_scratchpad():
    scratchpad = [
        {"thought": "Need to query net worth.", "action": "net_worth", "observation": "₹10,00,000"},
        {"thought": "Have the answer.", "final_answer": "Net worth ₹10,00,000."},
    ]
    a = AgentAnswer.from_agent_result(
        response="Your net worth is ₹10,00,000.",
        scratchpad=scratchpad,
        confidence_score=0.95,
    )
    assert len(a.reasoning_steps) == 2
    assert "Thought: Need to query net worth." in a.reasoning_steps[0]
    assert "Action: net_worth" in a.reasoning_steps[0]
    assert "Observation: ₹10,00,000" in a.reasoning_steps[0]
    assert "Final Answer:" in a.reasoning_steps[1]


def test_agent_answer_from_agent_result_none_confidence_defaults_to_1():
    a = AgentAnswer.from_agent_result(response="ok", scratchpad=None, confidence_score=None)
    assert a.confidence == 1.0


def test_agent_answer_from_agent_result_empty_scratchpad():
    a = AgentAnswer.from_agent_result(response="ok", scratchpad=[], confidence_score=0.8)
    assert a.reasoning_steps == []
    assert a.confidence == 0.8


def test_agent_answer_supporting_data_round_trip():
    data = [{"tool": "category_analysis", "category": "FOOD", "amount_paise": 450000}]
    a = AgentAnswer(answer="You spent ₹4,500.", supporting_data=data)
    assert a.supporting_data[0]["amount_paise"] == 450000


# ── Router — Phase 3 response fields ─────────────────────────────────────────

OWNER_ID = str(uuid.uuid4())


def _mock_result(confidence: float = 0.9, scratchpad: list | None = None) -> dict:
    return {
        "response": "You spent ₹5,000 on groceries.",
        "tool_calls": ["category_analysis"],
        "messages": [],
        "scratchpad": scratchpad or [],
        "session_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "confidence_score": confidence,
        "reflection_notes": "Complete answer.",
        "plan": None,
        "step_observations": [],
    }


@pytest.mark.asyncio
async def test_chat_response_includes_phase3_fields(async_client):
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=_mock_result(0.85))
        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "How much on groceries?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "confidence" in data
    assert "reasoning_steps" in data
    assert "supporting_data" in data
    assert isinstance(data["confidence"], float)
    assert isinstance(data["reasoning_steps"], list)
    assert isinstance(data["supporting_data"], list)


@pytest.mark.asyncio
async def test_chat_response_confidence_reflects_agent_score(async_client):
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=_mock_result(0.72))
        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "What is my balance?"},
        )

    assert resp.status_code == 200
    assert resp.json()["confidence"] == 0.72


@pytest.mark.asyncio
async def test_chat_response_no_confidence_defaults_to_1(async_client):
    result = _mock_result()
    result["confidence_score"] = None
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=result)
        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "Test"},
        )

    assert resp.status_code == 200
    assert resp.json()["confidence"] == 1.0


@pytest.mark.asyncio
async def test_chat_response_reasoning_steps_populated_from_scratchpad(async_client):
    """scratchpad extracted by agent.py must flow through to reasoning_steps in the response."""
    scratchpad = [
        {"thought": "Need to check groceries spend.", "action": "category_analysis", "observation": "₹5,000"},
        {"thought": "Have the answer.", "final_answer": "You spent ₹5,000."},
    ]
    with patch("api.routers.agent.ArthaAgent") as MockAgent:
        MockAgent.return_value.chat = AsyncMock(return_value=_mock_result(0.9, scratchpad=scratchpad))
        resp = await async_client.post(
            "/agent/chat",
            json={"owner_id": OWNER_ID, "message": "How much on groceries?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["reasoning_steps"]) == 2
    assert "Thought: Need to check groceries spend." in data["reasoning_steps"][0]
    assert "Action: category_analysis" in data["reasoning_steps"][0]
    assert "Final Answer:" in data["reasoning_steps"][1]
