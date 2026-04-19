"""
InvestmentAgent — portfolio and net-worth domain.

Tools exposed:
  - net_worth        : total net worth breakdown by asset class
  - portfolio_value  : per-instrument detail with NAV, units, gain/loss
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from services.agent.tools.registry import NetWorthInput, PortfolioValueInput
from services.agent.tools.net_worth import run as net_worth_run
from services.agent.tools.portfolio_value import run as portfolio_value_run
from services.agents._common.base_agent import BaseAgent

_INVESTMENT_TOOLS: list[tuple] = [
    ("net_worth", net_worth_run, NetWorthInput),
    ("portfolio_value", portfolio_value_run, PortfolioValueInput),
]


class InvestmentAgent(BaseAgent):
    """Domain agent for portfolio analysis and net-worth tracking."""

    AGENT_ID = "investment_agent"
    CAPABILITIES = ["investment", "portfolio", "net_worth"]

    def _build_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool(
                name=name,
                description=fn.__doc__ or name,
                args_schema=schema,
                coroutine=self._make_tool_bound(fn),
            )
            for name, fn, schema in _INVESTMENT_TOOLS
        ]
