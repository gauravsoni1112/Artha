"""
RiskAgent — financial risk assessment domain.

Tools exposed (all Phase 4 new tools):
  - emergency_fund_months  : months of expenses covered by liquid savings
  - asset_concentration    : portfolio concentration by asset class
  - debt_to_income         : DTI ratio from transaction history
  - insurance_coverage_gap : life and health insurance gap vs. income-based benchmark
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from services.agent.tools.registry import (
    AssetConcentrationInput,
    DebtToIncomeInput,
    EmergencyFundMonthsInput,
    InsuranceCoverageGapInput,
)
from services.agent.tools.asset_concentration import run as asset_concentration_run
from services.agent.tools.debt_to_income import run as debt_to_income_run
from services.agent.tools.emergency_fund_months import run as emergency_fund_months_run
from services.agent.tools.insurance_coverage_gap import run as insurance_coverage_gap_run
from services.agents._common.base_agent import BaseAgent
from libs.schemas.user_profile import UserProfile

_RISK_TOOLS: list[tuple] = [
    ("emergency_fund_months", emergency_fund_months_run, EmergencyFundMonthsInput),
    ("asset_concentration", asset_concentration_run, AssetConcentrationInput),
    ("debt_to_income", debt_to_income_run, DebtToIncomeInput),
    ("insurance_coverage_gap", insurance_coverage_gap_run, InsuranceCoverageGapInput),
]


class RiskAgent(BaseAgent):
    """
    Domain agent for personal finance risk assessment.

    Assesses emergency fund adequacy, portfolio concentration, debt burden,
    and insurance coverage gaps. Returns risk_level and structured findings
    for each dimension.
    """

    AGENT_ID = "risk_agent"
    CAPABILITIES = ["risk", "insurance", "emergency_fund", "debt"]

    def _build_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool(
                name=name,
                description=fn.__doc__ or name,
                args_schema=schema,
                coroutine=self._make_tool_bound(fn),
            )
            for name, fn, schema in _RISK_TOOLS
        ]

    def _system_prompt(self, user_profile: UserProfile) -> str:
        annual_income_paise = user_profile.total_monthly_income_paise * 12
        return (
            f"You are Artha, a personal finance risk advisor for {user_profile.name}. "
            f"You specialise in {', '.join(self.CAPABILITIES)} assessment. "
            "Use tools to retrieve real data — never guess amounts. "
            f"The user's annual income is approximately ₹{annual_income_paise / 100:,.0f}. "
            f"Family scope: {'yes' if user_profile.is_family_scope else 'no'}. "
            "When calling insurance_coverage_gap, pass annual_income_paise="
            f"{annual_income_paise} and is_family_scope={str(user_profile.is_family_scope).lower()}. "
            "Express amounts in Indian Rupee format (₹X,XX,XXX.XX). "
            "Reference fiscal year (April–March) for annual figures. "
            "Provide clear risk ratings (healthy / adequate / caution / elevated / critical) "
            "for each dimension assessed."
        )
