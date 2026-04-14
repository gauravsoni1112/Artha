"""
Unit tests for ReflectionNode.

All LLM calls are mocked — no API key or Docker required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.reflection import (
    MAX_REFLECT_ITERATIONS,
    REFLECTION_THRESHOLD,
    ReflectionNode,
    ReflectionResult,
)


# ── ReflectionResult helpers ──────────────────────────────────────────────────

def test_high_confidence_factory():
    r = ReflectionResult.high_confidence()
    assert r.confidence_score == 1.0
    assert r.is_complete is True
    assert r.needs_rerun is False


def test_fallback_factory():
    r = ReflectionResult.fallback()
    assert r.confidence_score == 0.5
    assert r.needs_rerun is False


# ── ReflectionNode._parse ─────────────────────────────────────────────────────

def _make_node() -> ReflectionNode:
    return ReflectionNode(llm=MagicMock())


def test_parse_valid_high_confidence():
    node = _make_node()
    payload = json.dumps({
        "confidence_score": 0.95,
        "is_complete": True,
        "reflection_notes": "Answer is complete.",
    })
    result = node._parse(payload)
    assert result.confidence_score == 0.95
    assert result.is_complete is True
    assert result.needs_rerun is False


def test_parse_valid_low_confidence_triggers_rerun():
    node = _make_node()
    payload = json.dumps({
        "confidence_score": 0.4,
        "is_complete": False,
        "reflection_notes": "Missing Q2 data.",
    })
    result = node._parse(payload)
    assert result.confidence_score == 0.4
    assert result.needs_rerun is True


def test_parse_clamps_score_above_1():
    node = _make_node()
    payload = json.dumps({"confidence_score": 1.5, "is_complete": True, "reflection_notes": ""})
    result = node._parse(payload)
    assert result.confidence_score == 1.0


def test_parse_clamps_score_below_0():
    node = _make_node()
    payload = json.dumps({"confidence_score": -0.3, "is_complete": False, "reflection_notes": "bad"})
    result = node._parse(payload)
    assert result.confidence_score == 0.0


def test_parse_empty_string_returns_fallback():
    node = _make_node()
    result = node._parse("")
    assert result.confidence_score == 0.5
    assert result.needs_rerun is False


def test_parse_invalid_json_returns_fallback():
    node = _make_node()
    result = node._parse("{not json}")
    assert result.confidence_score == 0.5


def test_parse_json_in_markdown_fences():
    node = _make_node()
    content = (
        "```json\n"
        '{"confidence_score": 0.8, "is_complete": true, "reflection_notes": "Good."}\n'
        "```"
    )
    result = node._parse(content)
    assert result.confidence_score == 0.8
    assert result.is_complete is True


# ── ReflectionNode.acall (async) ──────────────────────────────────────────────

def _ai_msg(content: str):
    m = MagicMock()
    m.content = content
    m.tool_calls = []
    type(m).__name__ = "AIMessage"
    return m


def _human_msg(content: str):
    from langchain_core.messages import HumanMessage
    return HumanMessage(content=content)


@pytest.mark.asyncio
async def test_acall_high_confidence_no_rerun():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "confidence_score": 0.9,
        "is_complete": True,
        "reflection_notes": "Complete answer.",
    })
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    node = ReflectionNode(llm=mock_llm)
    state = {
        "messages": [
            _human_msg("[owner_id=abc] What is my net worth?"),
            _ai_msg("Your net worth is ₹50,00,000."),
        ],
        "reflect_count": 0,
    }
    result = await node.acall(state)
    assert result["confidence_score"] == 0.9
    assert result["needs_rerun"] is False
    assert result["reflect_count"] == 1


@pytest.mark.asyncio
async def test_acall_low_confidence_triggers_rerun():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "confidence_score": 0.3,
        "is_complete": False,
        "reflection_notes": "Q2 data missing.",
    })
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    node = ReflectionNode(llm=mock_llm)
    state = {
        "messages": [
            _human_msg("Compare Q1 vs Q2 spending"),
            _ai_msg("Q1 data found but Q2 data unavailable."),
        ],
        "reflect_count": 0,
    }
    result = await node.acall(state)
    assert result["needs_rerun"] is True
    assert result["reflect_count"] == 1


@pytest.mark.asyncio
async def test_acall_max_iterations_stops_rerun():
    """After MAX_REFLECT_ITERATIONS, needs_rerun is always False."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "confidence_score": 0.2,
        "is_complete": False,
        "reflection_notes": "Still incomplete.",
    })
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    node = ReflectionNode(llm=mock_llm)
    state = {
        "messages": [_human_msg("Question"), _ai_msg("Incomplete answer.")],
        "reflect_count": MAX_REFLECT_ITERATIONS,  # already at max
    }
    result = await node.acall(state)
    assert result["needs_rerun"] is False  # exhausted iterations


@pytest.mark.asyncio
async def test_acall_empty_messages_uses_fallback():
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()  # should not be called

    node = ReflectionNode(llm=mock_llm)
    result = await node.acall({"messages": [], "reflect_count": 0})
    assert result["confidence_score"] == 0.5
    assert result["needs_rerun"] is False
    mock_llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_acall_strips_owner_id_from_question():
    """owner_id token is stripped before sending question to reflection LLM."""
    captured_prompts = []

    async def mock_ainvoke(prompts):
        captured_prompts.extend(prompts)
        m = MagicMock()
        m.content = json.dumps({"confidence_score": 0.9, "is_complete": True, "reflection_notes": ""})
        return m

    mock_llm = MagicMock()
    mock_llm.ainvoke = mock_ainvoke

    node = ReflectionNode(llm=mock_llm)
    state = {
        "messages": [
            _human_msg("[owner_id=abc123] What is my balance?"),
            _ai_msg("Your balance is ₹10,000."),
        ],
        "reflect_count": 0,
    }
    await node.acall(state)

    # The human message sent to the reflection LLM should NOT contain owner_id
    human_content = captured_prompts[1].content
    assert "owner_id" not in human_content
    assert "What is my balance?" in human_content
