"""
Unit tests for PlannerNode and Plan schema.

All LLM calls are mocked — no API key or Docker required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.planner import Plan, PlannerNode


# ── Plan schema ───────────────────────────────────────────────────────────────

def test_plan_trivial_factory():
    plan = Plan.trivial("How much did I spend?")
    assert len(plan.steps) == 1
    assert plan.steps[0] == "How much did I spend?"
    assert "no decomposition" in plan.reasoning.lower()


def test_plan_rejects_empty_steps():
    with pytest.raises(Exception):
        Plan(steps=[], reasoning="test")


def test_plan_valid_multi_step():
    plan = Plan(
        steps=["What did I spend on groceries in Q1?", "What did I spend on groceries in Q2?"],
        reasoning="Requires two separate period lookups.",
    )
    assert len(plan.steps) == 2


# ── PlannerNode._parse_response ───────────────────────────────────────────────

def _make_planner(llm=None) -> PlannerNode:
    return PlannerNode(llm=llm or MagicMock())


def test_parse_valid_json():
    planner = _make_planner()
    payload = json.dumps({
        "steps": ["Query Q1 groceries", "Query Q2 groceries"],
        "reasoning": "Two period comparison.",
    })
    plan = planner._parse_response(payload, "original question")
    assert len(plan.steps) == 2
    assert plan.reasoning == "Two period comparison."


def test_parse_json_wrapped_in_markdown_fences():
    planner = _make_planner()
    payload = (
        "Sure! Here is the plan:\n"
        "```json\n"
        '{"steps": ["Step 1"], "reasoning": "Simple."}\n'
        "```"
    )
    plan = planner._parse_response(payload, "original")
    assert plan.steps == ["Step 1"]


def test_parse_empty_string_falls_back_to_trivial():
    planner = _make_planner()
    plan = planner._parse_response("", "original question")
    assert plan.steps == ["original question"]
    assert "no decomposition" in plan.reasoning.lower()


def test_parse_invalid_json_falls_back_to_trivial():
    planner = _make_planner()
    plan = planner._parse_response("{not valid json}", "my question")
    assert plan.steps == ["my question"]


def test_parse_json_missing_steps_key_falls_back_to_trivial():
    planner = _make_planner()
    plan = planner._parse_response('{"reasoning": "no steps key"}', "my question")
    assert plan.steps == ["my question"]


# ── PlannerNode._plan (sync) via mocked LLM ───────────────────────────────────

def test_plan_sync_calls_llm_and_parses():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "steps": ["Check income", "Check expenses"],
        "reasoning": "Two lookups.",
    })
    mock_llm.invoke.return_value = mock_response

    planner = PlannerNode(llm=mock_llm)
    plan = planner._plan("Compare my income and expenses.")

    assert len(plan.steps) == 2
    mock_llm.invoke.assert_called_once()


# ── PlannerNode.acall (async) via mocked LLM ─────────────────────────────────

@pytest.mark.asyncio
async def test_acall_returns_plan_and_messages():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "steps": ["Check groceries Q1", "Check groceries Q2"],
        "reasoning": "Quarter comparison.",
    })
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    from langchain_core.messages import HumanMessage
    planner = PlannerNode(llm=mock_llm)
    state = {"messages": [HumanMessage(content="[owner_id=abc] Compare groceries Q1 vs Q2")]}
    result = await planner.acall(state)

    assert isinstance(result["plan"], Plan)
    assert len(result["plan"].steps) == 2
    assert result["messages"] is state["messages"]


@pytest.mark.asyncio
async def test_acall_with_no_human_message_uses_empty_question():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({"steps": ["step"], "reasoning": "r"})
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    planner = PlannerNode(llm=mock_llm)
    result = await planner.acall({"messages": []})
    assert isinstance(result["plan"], Plan)


@pytest.mark.asyncio
async def test_acall_fallback_on_llm_bad_output():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "I cannot produce JSON right now."
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    from langchain_core.messages import HumanMessage
    planner = PlannerNode(llm=mock_llm)
    state = {"messages": [HumanMessage(content="What is my balance?")]}
    result = await planner.acall(state)

    # Fallback to trivial plan
    assert result["plan"].steps == ["What is my balance?"]
