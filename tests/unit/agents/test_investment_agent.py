"""Unit tests for InvestmentAgent — tool selection and class attributes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.agents.investment.agent import InvestmentAgent, _INVESTMENT_TOOLS

_EXPECTED_TOOLS = {"net_worth", "portfolio_value"}


def test_agent_id():
    assert InvestmentAgent.AGENT_ID == "investment_agent"


def test_capabilities():
    caps = InvestmentAgent.CAPABILITIES
    assert "investment" in caps
    assert "portfolio" in caps
    assert "net_worth" in caps


def test_tool_names_declared():
    assert {name for name, _, _ in _INVESTMENT_TOOLS} == _EXPECTED_TOOLS


def test_tool_count():
    assert len(_INVESTMENT_TOOLS) == 2


def _make_agent() -> InvestmentAgent:
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_policy = MagicMock()
    mock_policy.build_chat_model.return_value = mock_llm
    mock_policy.destination = "local"
    with patch("services.agents._common.base_agent.RoutingPolicy") as mock_rp:
        mock_rp.from_env.return_value = mock_policy
        return InvestmentAgent(session_factory=MagicMock())


def test_build_tools_names():
    assert {t.name for t in _make_agent()._build_tools("00000000-0000-0000-0000-000000000001")} == _EXPECTED_TOOLS


def test_build_tools_are_async():
    for t in _make_agent()._build_tools("00000000-0000-0000-0000-000000000001"):
        assert t.coroutine is not None


def test_system_prompt_mentions_investment():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Ananya"
    profile.risk_appetite = "aggressive"
    prompt = agent._system_prompt(profile)
    assert "Ananya" in prompt
    assert any(cap in prompt for cap in InvestmentAgent.CAPABILITIES)
