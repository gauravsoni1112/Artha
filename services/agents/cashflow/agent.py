"""
CashflowAgent — cashflow, spending, and budgeting domain.

Tools exposed:
  - transaction_query    : fetch raw transactions by date / category / account
  - category_analysis    : spending breakdown by category (totals + %)
  - spending_trend       : month-over-month trend per category or overall
  - budget_comparison    : actual vs. budgeted spend for a period
  - upcoming_expenses    : predict recurring expenses in the next N days

All tools are thin wrappers over the shared Phase 3 tool implementations
in services/agent/tools/; the agent only binds the subset it needs so
the LLM is not overwhelmed by irrelevant tool choices.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from services.agent.tools.registry import (
    BudgetComparisonInput,
    CategoryAnalysisInput,
    SpendingTrendInput,
    TransactionQueryInput,
    UpcomingExpensesInput,
)
from services.agent.tools.budget_comparison import run as budget_comparison_run
from services.agent.tools.category_analysis import run as category_analysis_run
from services.agent.tools.spending_trend import run as spending_trend_run
from services.agent.tools.transaction_query import run as transaction_query_run
from services.agent.tools.upcoming_expenses import run as upcoming_expenses_run
from services.agents._common.base_agent import BaseAgent

# Tools exposed by this agent (subset of the full Phase 3 registry)
_CASHFLOW_TOOLS: list[tuple] = [
    ("transaction_query", transaction_query_run, TransactionQueryInput),
    ("category_analysis", category_analysis_run, CategoryAnalysisInput),
    ("spending_trend", spending_trend_run, SpendingTrendInput),
    ("budget_comparison", budget_comparison_run, BudgetComparisonInput),
    ("upcoming_expenses", upcoming_expenses_run, UpcomingExpensesInput),
]


class CashflowAgent(BaseAgent):
    """
    Domain agent for cashflow, spending, and budget analysis.

    Receives an AgentRequest, runs the planner→executor→reflect loop with
    the 5 cashflow tools, and returns a fully-populated AgentResponse.
    """

    AGENT_ID = "cashflow_agent"
    CAPABILITIES = ["cashflow", "spending", "budget"]

    def _build_tools(self) -> list[StructuredTool]:
        """Return the 5 cashflow-domain LangChain tools with the DB session bound."""
        session = self._session
        tools = []
        for name, fn, schema in _CASHFLOW_TOOLS:
            async def _bound(session=session, fn=fn, **kwargs):
                return (await fn(session=session, **kwargs)).to_llm_str()

            tools.append(
                StructuredTool(
                    name=name,
                    description=fn.__doc__ or name,
                    args_schema=schema,
                    coroutine=_bound,
                )
            )
        return tools
