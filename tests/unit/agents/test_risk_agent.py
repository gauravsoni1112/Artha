"""
Unit tests for RiskAgent — tool selection, class attributes, and system prompt.

Also covers the 4 new Phase 4 risk tool input schemas.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.agents.risk.agent import RiskAgent, _RISK_TOOLS
from services.agent.tools.registry import (
    EmergencyFundMonthsInput,
    AssetConcentrationInput,
    DebtToIncomeInput,
    InsuranceCoverageGapInput,
)

_EXPECTED_TOOLS = {
    "emergency_fund_months",
    "asset_concentration",
    "debt_to_income",
    "insurance_coverage_gap",
}


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------


def test_agent_id():
    assert RiskAgent.AGENT_ID == "risk_agent"


def test_capabilities():
    caps = RiskAgent.CAPABILITIES
    assert "risk" in caps
    assert "insurance" in caps
    assert "emergency_fund" in caps
    assert "debt" in caps


def test_capabilities_count():
    assert len(RiskAgent.CAPABILITIES) == 4


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def test_risk_tool_names_declared():
    assert {name for name, _, _ in _RISK_TOOLS} == _EXPECTED_TOOLS


def test_risk_tools_count():
    assert len(_RISK_TOOLS) == 4


def test_risk_tools_have_schemas():
    for name, fn, schema in _RISK_TOOLS:
        assert schema is not None, f"tool '{name}' has no schema"


# ---------------------------------------------------------------------------
# _build_tools
# ---------------------------------------------------------------------------


def _make_agent() -> RiskAgent:
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    with patch("services.agents._common.base_agent.agent_llm_config") as mock_cfg:
        mock_cfg.return_value.build_chat_model.return_value = mock_llm
        return RiskAgent(session_factory=MagicMock())


def test_build_tools_names():
    assert {t.name for t in _make_agent()._build_tools()} == _EXPECTED_TOOLS


def test_build_tools_are_async():
    for t in _make_agent()._build_tools():
        assert t.coroutine is not None, f"tool '{t.name}' is not async"


def test_build_tools_have_descriptions():
    for t in _make_agent()._build_tools():
        assert t.description, f"tool '{t.name}' has no description"


# ---------------------------------------------------------------------------
# System prompt — risk-agent overrides _system_prompt to embed income context
# ---------------------------------------------------------------------------


def test_system_prompt_embeds_income():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Vikram"
    profile.risk_appetite = "moderate"
    profile.total_monthly_income_paise = 100_000 * 100  # ₹1L/mo
    profile.is_family_scope = False

    prompt = agent._system_prompt(profile)
    assert "Vikram" in prompt
    # annual income injected for insurance_coverage_gap tool hint
    assert "annual_income_paise" in prompt


def test_system_prompt_family_scope():
    agent = _make_agent()
    profile = MagicMock()
    profile.name = "Priya"
    profile.risk_appetite = "conservative"
    profile.total_monthly_income_paise = 80_000 * 100
    profile.is_family_scope = True

    prompt = agent._system_prompt(profile)
    assert "true" in prompt.lower() or "True" in prompt


# ---------------------------------------------------------------------------
# Input schema defaults — risk tool schemas
# ---------------------------------------------------------------------------


def test_emergency_fund_defaults():
    inp = EmergencyFundMonthsInput(owner_id="00000000-0000-0000-0000-000000000001")
    assert inp.expense_months == 3


def test_asset_concentration_defaults():
    inp = AssetConcentrationInput(owner_id="00000000-0000-0000-0000-000000000001")
    assert inp.concentration_threshold_pct == pytest.approx(40.0)


def test_debt_to_income_defaults():
    inp = DebtToIncomeInput(owner_id="00000000-0000-0000-0000-000000000001")
    assert inp.months == 3


def test_insurance_coverage_gap_defaults():
    inp = InsuranceCoverageGapInput(owner_id="00000000-0000-0000-0000-000000000001")
    assert inp.annual_income_paise == 0
    assert inp.is_family_scope is False
    assert inp.existing_life_cover_paise == 0
    assert inp.existing_health_cover_paise == 0
