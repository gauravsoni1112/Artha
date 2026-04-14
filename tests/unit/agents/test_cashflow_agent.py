"""
Unit tests for CashflowAgent — tool selection, capabilities, and envelope shape.

We do NOT exercise the LLM or DB here; those are integration concerns.
All tests use MagicMock for the AsyncSession and patch out build_chat_model
so no real LLM config is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agents.cashflow.agent import CashflowAgent, _CASHFLOW_TOOLS


# ---------------------------------------------------------------------------
# Class-level attributes — no constructor needed
# ---------------------------------------------------------------------------


def test_agent_id():
    assert CashflowAgent.AGENT_ID == "cashflow_agent"


def test_capabilities_contain_expected_tags():
    caps = CashflowAgent.CAPABILITIES
    assert "cashflow" in caps
    assert "spending" in caps
    assert "budget" in caps


def test_capabilities_length():
    assert len(CashflowAgent.CAPABILITIES) == 3


# ---------------------------------------------------------------------------
# Tool registry — verify the 5 expected tools are declared
# ---------------------------------------------------------------------------


_EXPECTED_TOOL_NAMES = {
    "transaction_query",
    "category_analysis",
    "spending_trend",
    "budget_comparison",
    "upcoming_expenses",
}


def test_cashflow_tool_names_match_expected():
    declared = {name for name, _, _ in _CASHFLOW_TOOLS}
    assert declared == _EXPECTED_TOOL_NAMES


def test_cashflow_tools_count():
    assert len(_CASHFLOW_TOOLS) == 5


def test_cashflow_tools_have_schemas():
    """Every tool entry must have a non-None Pydantic schema class."""
    for name, fn, schema in _CASHFLOW_TOOLS:
        assert schema is not None, f"tool '{name}' has no schema"


# ---------------------------------------------------------------------------
# _build_tools — verify returned StructuredTool objects have correct names
# ---------------------------------------------------------------------------


def _make_agent() -> CashflowAgent:
    """Construct CashflowAgent with a mocked session and LLM."""
    mock_session = MagicMock()
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    with patch(
        "services.agents._common.base_agent.agent_llm_config"
    ) as mock_cfg:
        mock_cfg.return_value.build_chat_model.return_value = mock_llm
        agent = CashflowAgent(session=mock_session)
    return agent


def test_build_tools_returns_five_tools():
    agent = _make_agent()
    tools = agent._build_tools()
    assert len(tools) == 5


def test_build_tools_names():
    agent = _make_agent()
    tool_names = {t.name for t in agent._build_tools()}
    assert tool_names == _EXPECTED_TOOL_NAMES


def test_build_tools_are_async():
    """All cashflow tools must be coroutine-based (async)."""
    agent = _make_agent()
    for tool in agent._build_tools():
        assert tool.coroutine is not None, f"tool '{tool.name}' is not async"


def test_build_tools_have_descriptions():
    agent = _make_agent()
    for tool in agent._build_tools():
        assert tool.description, f"tool '{tool.name}' has no description"


# ---------------------------------------------------------------------------
# System prompt — domain keywords present
# ---------------------------------------------------------------------------


def test_system_prompt_contains_capabilities():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Ravi"
    profile.risk_appetite = "moderate"

    prompt = agent._system_prompt(profile)
    assert "cashflow" in prompt
    assert "spending" in prompt
    assert "budget" in prompt


def test_system_prompt_mentions_user_name():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Priya"
    profile.risk_appetite = "conservative"

    prompt = agent._system_prompt(profile)
    assert "Priya" in prompt


def test_system_prompt_mentions_fiscal_year():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Test"
    profile.risk_appetite = "moderate"

    prompt = agent._system_prompt(profile)
    assert "fiscal year" in prompt.lower() or "April" in prompt
