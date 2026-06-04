"""
Unit tests for PlannerNode and Plan schema.

All LLM calls are mocked — no API key or Docker required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.planner import Plan, PlannerNode


# ── Plan schema ───────────────────────────────────────────────────────────────

def test_plan_trivial_factory():
    plan = Plan.trivial("How much did I spend?")
    assert len(plan.steps) == 1
    assert plan.steps[0] == "How much did I spend?"
    assert "no decomposition" in plan.reasoning.lower()
    assert plan.confidence == 1.0
    assert plan.confidence_reason != ""


def test_plan_rejects_empty_steps():
    with pytest.raises(Exception):
        Plan(steps=[], reasoning="test")


def test_plan_valid_multi_step():
    plan = Plan(
        steps=["What did I spend on groceries in Q1?", "What did I spend on groceries in Q2?"],
        reasoning="Requires two separate period lookups.",
    )
    assert len(plan.steps) == 2
    assert plan.confidence == 1.0  # default


def test_plan_confidence_out_of_range_raises():
    with pytest.raises(Exception):
        Plan(steps=["s"], reasoning="r", confidence=1.5)

    with pytest.raises(Exception):
        Plan(steps=["s"], reasoning="r", confidence=-0.1)


def test_plan_with_low_confidence():
    plan = Plan(
        steps=["What is my progress toward savings goals?", "What is my net worth?"],
        reasoning="Retirement readiness check.",
        confidence=0.6,
        confidence_reason="Assumed retirement goal exists; may not be set up.",
    )
    assert plan.confidence == 0.6
    assert "retirement" in plan.confidence_reason.lower()


# ── PlannerNode._plan (sync) via mocked LLM ───────────────────────────────────

def _make_planner_mock(return_plan: Plan | None = None, raises: Exception | None = None) -> tuple[PlannerNode, MagicMock]:
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    if raises is not None:
        mock_structured.invoke.side_effect = raises
        mock_structured.ainvoke = AsyncMock(side_effect=raises)
    else:
        plan = return_plan or Plan(steps=["Default step"], reasoning="Default.")
        mock_structured.invoke.return_value = plan
        mock_structured.ainvoke = AsyncMock(return_value=plan)
    return PlannerNode(llm=mock_llm), mock_llm


def test_plan_sync_calls_llm_and_parses():
    expected = Plan(
        steps=["Check income", "Check expenses"],
        reasoning="Two lookups.",
        confidence=0.9,
        confidence_reason="Clear comparison query.",
    )
    planner, mock_llm = _make_planner_mock(return_plan=expected)

    plan = planner._plan("Compare my income and expenses.")

    assert len(plan.steps) == 2
    assert plan.reasoning == "Two lookups."
    assert plan.confidence == 0.9
    assert plan.confidence_reason == "Clear comparison query."
    mock_llm.with_structured_output.return_value.invoke.assert_called_once()


def test_plan_sync_falls_back_on_error():
    planner, _ = _make_planner_mock(raises=ValueError("LLM error"))
    plan = planner._plan("What is my balance?")
    assert plan.steps == ["What is my balance?"]
    assert "no decomposition" in plan.reasoning.lower()


# ── PlannerNode.acall (async) via mocked LLM ─────────────────────────────────

@pytest.mark.asyncio
async def test_acall_returns_plan_and_messages():
    expected = Plan(steps=["Check groceries Q1", "Check groceries Q2"], reasoning="Quarter comparison.")
    planner, _ = _make_planner_mock(return_plan=expected)

    from langchain_core.messages import HumanMessage
    state = {"messages": [HumanMessage(content="[owner_id=abc] Compare groceries Q1 vs Q2")]}
    result = await planner.acall(state)

    assert isinstance(result["plan"], Plan)
    assert len(result["plan"].steps) == 2
    assert result["messages"] is state["messages"]


@pytest.mark.asyncio
async def test_acall_with_no_human_message_uses_empty_question():
    expected = Plan(steps=["step"], reasoning="r")
    planner, _ = _make_planner_mock(return_plan=expected)
    result = await planner.acall({"messages": []})
    assert isinstance(result["plan"], Plan)


@pytest.mark.asyncio
async def test_acall_fallback_on_llm_error():
    planner, _ = _make_planner_mock(raises=ValueError("LLM unavailable"))

    from langchain_core.messages import HumanMessage
    state = {"messages": [HumanMessage(content="What is my balance?")]}
    result = await planner.acall(state)

    assert result["plan"].steps == ["What is my balance?"]
