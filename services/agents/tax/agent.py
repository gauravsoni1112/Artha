"""
TaxAgent — tax computation and ITR-filing domain.

Tools exposed:
  - tax_summary       : ITR/tax record per fiscal year; falls back to transaction estimate
  - transaction_query : raw transaction detail for tax-related categorisation queries
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from services.agent.tools.registry import TaxSummaryInput, TransactionQueryInput
from services.agent.tools.tax_summary import run as tax_summary_run
from services.agent.tools.transaction_query import run as transaction_query_run
from services.agents._common.base_agent import BaseAgent

_TAX_TOOLS: list[tuple] = [
    ("tax_summary", tax_summary_run, TaxSummaryInput),
    ("transaction_query", transaction_query_run, TransactionQueryInput),
]


class TaxAgent(BaseAgent):
    """Domain agent for tax planning, ITR filing support, and fiscal-year analysis."""

    AGENT_ID = "tax_agent"
    CAPABILITIES = ["tax", "itr", "fiscal"]

    def _build_tools(self, owner_id: str) -> list[StructuredTool]:
        return [
            StructuredTool(
                name=name,
                description=fn.__doc__ or name,
                args_schema=schema,
                coroutine=self._make_tool_bound(fn, owner_id),
            )
            for name, fn, schema in _TAX_TOOLS
        ]
