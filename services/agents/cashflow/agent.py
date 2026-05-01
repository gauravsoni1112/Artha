"""
CashflowAgent — cashflow, spending, and budgeting domain.

Tools exposed:
  - fetch_accounts       : list all accounts (bank, credit card, investment) with balances
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

from libs.schemas.user_profile import UserProfile
from services.agent.tools.registry import (
    BudgetComparisonInput,
    CategoryAnalysisInput,
    FetchAccountsInput,
    SpendingTrendInput,
    TransactionQueryInput,
    UpcomingExpensesInput,
)
from services.agent.tools.budget_comparison import run as budget_comparison_run
from services.agent.tools.category_analysis import run as category_analysis_run
from services.agent.tools.fetch_accounts import run as fetch_accounts_run
from services.agent.tools.spending_trend import run as spending_trend_run
from services.agent.tools.transaction_query import run as transaction_query_run
from services.agent.tools.upcoming_expenses import run as upcoming_expenses_run
from services.agents._common.base_agent import BaseAgent

# Tools exposed by this agent (subset of the full Phase 3 registry)
_CASHFLOW_TOOLS: list[tuple] = [
    ("fetch_accounts", fetch_accounts_run, FetchAccountsInput),
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
    CAPABILITIES = ["cashflow", "spending", "budget", "accounts"]

    def _system_prompt(self, user_profile: UserProfile) -> str:
        base = super()._system_prompt(user_profile)
        return base + (
            "\n\nTool selection guide:\n"
            "- fetch_accounts: List accounts with balances. Call first if the user mentions a "
            "specific account by name.\n"
            "- transaction_query: Fetch individual transactions. Use when the user wants to see "
            "a LIST of specific entries, or when filtering by a single account.\n"
            "- category_analysis: Aggregate spending by category. Prefer over transaction_query "
            "when the user asks 'how much did I spend on X' or wants a category breakdown.\n"
            "- spending_trend: Month-by-month trend. Use when the user asks 'is my spending "
            "going up?' or wants a comparison across months.\n"
            "- budget_comparison: Actual vs budget. Use when the user asks about budgets.\n"
            "- upcoming_expenses: Predicted recurring bills. Use for 'what bills are coming?'."
        )

    def _build_tools(self, owner_id: str) -> list[StructuredTool]:
        return [
            StructuredTool(
                name=name,
                description=fn.__doc__ or name,
                args_schema=schema,
                coroutine=self._make_tool_bound(fn, owner_id),
            )
            for name, fn, schema in _CASHFLOW_TOOLS
        ]
