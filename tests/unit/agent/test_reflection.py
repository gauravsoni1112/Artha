"""
Unit tests for ReflectionNode.

All LLM calls are mocked — no API key or Docker required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.reflection import (
    MAX_REFLECT_ITERATIONS,
    REFLECTION_THRESHOLD,
    ReflectionNode,
    ReflectionResult,
    _LLMReflection,
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


# ── _LLMReflection schema ─────────────────────────────────────────────────────

def test_llm_reflection_rejects_score_above_1():
    with pytest.raises(Exception):
        _LLMReflection(confidence_score=1.5, is_complete=True, reflection_notes="")


def test_llm_reflection_rejects_score_below_0():
    with pytest.raises(Exception):
        _LLMReflection(confidence_score=-0.1, is_complete=False, reflection_notes="bad")


def test_llm_reflection_valid():
    r = _LLMReflection(confidence_score=0.8, is_complete=True, reflection_notes="Good.")
    assert r.confidence_score == 0.8


# ── ReflectionNode mock helpers ───────────────────────────────────────────────

def _make_node(llm_output: _LLMReflection | None = None, raises: Exception | None = None) -> ReflectionNode:
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    if raises is not None:
        mock_structured.ainvoke = AsyncMock(side_effect=raises)
    else:
        out = llm_output or _LLMReflection(confidence_score=0.9, is_complete=True, reflection_notes="Complete.")
        mock_structured.ainvoke = AsyncMock(return_value=out)
    return ReflectionNode(llm=mock_llm)


def _ai_msg(content: str):
    m = MagicMock()
    m.content = content
    m.tool_calls = []
    type(m).__name__ = "AIMessage"
    return m


def _human_msg(content: str):
    from langchain_core.messages import HumanMessage
    return HumanMessage(content=content)


# ── ReflectionNode.acall (async) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acall_high_confidence_no_rerun():
    node = _make_node(_LLMReflection(confidence_score=0.9, is_complete=True, reflection_notes="Complete answer."))
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
    node = _make_node(_LLMReflection(confidence_score=0.3, is_complete=False, reflection_notes="Q2 data missing."))
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
async def test_acall_below_threshold_but_complete_triggers_rerun():
    """Score below REFLECTION_THRESHOLD triggers rerun even if is_complete=True."""
    node = _make_node(_LLMReflection(
        confidence_score=0.4,
        is_complete=True,
        reflection_notes="Answer present but time range not confirmed.",
    ))
    state = {
        "messages": [
            _human_msg("What did I spend last month?"),
            _ai_msg("You spent some amount on various categories."),
        ],
        "reflect_count": 0,
    }
    result = await node.acall(state)
    assert result["needs_rerun"] is True
    assert result["reflect_count"] == 1


@pytest.mark.asyncio
async def test_acall_max_iterations_stops_rerun():
    """After MAX_REFLECT_ITERATIONS, needs_rerun is always False."""
    node = _make_node(_LLMReflection(confidence_score=0.2, is_complete=False, reflection_notes="Still incomplete."))
    state = {
        "messages": [_human_msg("Question"), _ai_msg("Incomplete answer.")],
        "reflect_count": MAX_REFLECT_ITERATIONS,
    }
    result = await node.acall(state)
    assert result["needs_rerun"] is False


@pytest.mark.asyncio
async def test_acall_empty_messages_uses_fallback():
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.ainvoke = AsyncMock()

    node = ReflectionNode(llm=mock_llm)
    result = await node.acall({"messages": [], "reflect_count": 0})
    assert result["confidence_score"] == 0.5
    assert result["needs_rerun"] is False
    mock_structured.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_acall_llm_error_uses_fallback():
    node = _make_node(raises=ValueError("LLM unavailable"))
    state = {
        "messages": [
            _human_msg("What is my balance?"),
            _ai_msg("Your balance is ₹10,000."),
        ],
        "reflect_count": 0,
    }
    result = await node.acall(state)
    assert result["confidence_score"] == 0.5
    assert result["needs_rerun"] is False


@pytest.mark.asyncio
async def test_acall_uses_first_human_message_as_question():
    """The first HumanMessage is used as the question in the reflection prompt."""
    captured_prompts: list = []

    async def mock_ainvoke(prompts, **kwargs):
        captured_prompts.extend(prompts)
        return _LLMReflection(confidence_score=0.9, is_complete=True, reflection_notes="")

    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.ainvoke = mock_ainvoke

    node = ReflectionNode(llm=mock_llm)
    state = {
        "messages": [
            _human_msg("What is my balance?"),
            _ai_msg("Your balance is ₹10,000."),
        ],
        "reflect_count": 0,
    }
    await node.acall(state)

    human_content = captured_prompts[1].content
    assert "What is my balance?" in human_content
