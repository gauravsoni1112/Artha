"""Unit tests for GoalAgent — tool selection and class attributes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.agents.goal.agent import GoalAgent, _GOAL_TOOLS

_EXPECTED_TOOLS = {"goal_progress", "upcoming_expenses"}


def test_agent_id():
    assert GoalAgent.AGENT_ID == "goal_agent"


def test_capabilities():
    caps = GoalAgent.CAPABILITIES
    assert "goal" in caps
    assert "planning" in caps
    assert "savings" in caps


def test_tool_names_declared():
    assert {name for name, _, _ in _GOAL_TOOLS} == _EXPECTED_TOOLS


def test_tool_count():
    assert len(_GOAL_TOOLS) == 2


def _make_agent() -> GoalAgent:
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_policy = MagicMock()
    mock_policy.build_chat_model.return_value = mock_llm
    mock_policy.destination = "local"
    with patch("services.agents._common.base_agent.RoutingPolicy") as mock_rp:
        mock_rp.from_env.return_value = mock_policy
        return GoalAgent(session_factory=MagicMock())


def test_build_tools_names():
    assert {t.name for t in _make_agent()._build_tools("00000000-0000-0000-0000-000000000001")} == _EXPECTED_TOOLS


def test_build_tools_are_async():
    for t in _make_agent()._build_tools("00000000-0000-0000-0000-000000000001"):
        assert t.coroutine is not None


def test_system_prompt_mentions_goal():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Meera"
    profile.risk_appetite = "conservative"
    prompt = agent._system_prompt(profile)
    assert "Meera" in prompt
    assert any(cap in prompt for cap in GoalAgent.CAPABILITIES)
