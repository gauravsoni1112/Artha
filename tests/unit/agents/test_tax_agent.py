"""Unit tests for TaxAgent — tool selection and class attributes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.agents.tax.agent import TaxAgent, _TAX_TOOLS

_EXPECTED_TOOLS = {"tax_summary", "transaction_query"}


def test_agent_id():
    assert TaxAgent.AGENT_ID == "tax_agent"


def test_capabilities():
    caps = TaxAgent.CAPABILITIES
    assert "tax" in caps
    assert "itr" in caps
    assert "fiscal" in caps


def test_tool_names_declared():
    assert {name for name, _, _ in _TAX_TOOLS} == _EXPECTED_TOOLS


def test_tool_count():
    assert len(_TAX_TOOLS) == 2


def _make_agent() -> TaxAgent:
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_policy = MagicMock()
    mock_policy.build_chat_model.return_value = mock_llm
    mock_policy.destination = "local"
    with patch("services.agents._common.base_agent.RoutingPolicy") as mock_rp:
        mock_rp.from_env.return_value = mock_policy
        return TaxAgent(session_factory=MagicMock())


def test_build_tools_names():
    assert {t.name for t in _make_agent()._build_tools()} == _EXPECTED_TOOLS


def test_build_tools_are_async():
    for t in _make_agent()._build_tools():
        assert t.coroutine is not None


def test_system_prompt_mentions_tax():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Raj"
    profile.risk_appetite = "moderate"
    prompt = agent._system_prompt(profile)
    assert "Raj" in prompt
    assert any(cap in prompt for cap in TaxAgent.CAPABILITIES)
