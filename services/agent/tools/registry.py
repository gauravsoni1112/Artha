"""
Tool registry — maps tool names to their implementations and exposes
LangGraph-compatible tool definitions.

Adding a new tool:
  1. Implement it in services/agent/tools/<name>.py
  2. Import and register it here in TOOL_REGISTRY.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Coroutine

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent.tools.base import ToolResult
from services.agent.tools.transaction_query import run as transaction_query_run
from services.agent.tools.category_analysis import run as category_analysis_run
from services.agent.tools.net_worth import run as net_worth_run
from services.agent.tools.portfolio_value import run as portfolio_value_run
from services.agent.tools.tax_summary import run as tax_summary_run
from services.agent.tools.upcoming_expenses import run as upcoming_expenses_run
from services.agent.tools.spending_trend import run as spending_trend_run
from services.agent.tools.budget_comparison import run as budget_comparison_run
from services.agent.tools.goal_progress import run as goal_progress_run
# Phase 4 — risk-domain tools
from services.agent.tools.emergency_fund_months import run as emergency_fund_months_run
from services.agent.tools.asset_concentration import run as asset_concentration_run
from services.agent.tools.debt_to_income import run as debt_to_income_run
from services.agent.tools.insurance_coverage_gap import run as insurance_coverage_gap_run


# ── Input schemas (used by LangGraph for JSON schema extraction) ───────────────

class TransactionQueryInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    start_date: str | None = Field(None, description="Start date YYYY-MM-DD (inclusive)")
    end_date: str | None = Field(None, description="End date YYYY-MM-DD (inclusive)")
    category: str | None = Field(None, description="Transaction category filter e.g. GROCERIES")
    account_id: str | None = Field(None, description="Filter by specific account UUID")
    limit: int = Field(50, description="Max rows to return")


class CategoryAnalysisInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    start_date: str | None = Field(None, description="Start date YYYY-MM-DD")
    end_date: str | None = Field(None, description="End date YYYY-MM-DD")
    fiscal_year: str | None = Field(None, description="Fiscal year e.g. 2024-25")


class NetWorthInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")


class PortfolioValueInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    asset_class: str | None = Field(None, description="Filter by asset class e.g. MUTUAL_FUND, EQUITY")


class TaxSummaryInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    fiscal_year: str | None = Field(None, description="Fiscal year e.g. 2024-25; omit for all years")


class UpcomingExpensesInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    lookahead_days: int = Field(30, description="Days ahead to predict recurring expenses")


class SpendingTrendInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    category: str | None = Field(None, description="Category to trend e.g. GROCERIES; omit for all")
    months: int = Field(6, description="Number of months to include (default 6)")


class BudgetComparisonInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    start_date: str | None = Field(None, description="Start date YYYY-MM-DD")
    end_date: str | None = Field(None, description="End date YYYY-MM-DD")
    fiscal_year: str | None = Field(None, description="Fiscal year e.g. 2024-25")


class GoalProgressInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    goal_name: str | None = Field(None, description="Partial goal name filter; omit for all goals")


class EmergencyFundMonthsInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    expense_months: int = Field(3, description="Number of recent months used to compute avg expense (default 3)")


class AssetConcentrationInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    concentration_threshold_pct: float = Field(
        40.0, description="Flag asset classes above this % of total portfolio (default 40)"
    )


class DebtToIncomeInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    months: int = Field(3, description="Number of recent months to average over (default 3)")


class InsuranceCoverageGapInput(BaseModel):
    owner_id: str = Field(description="UUID of the owner")
    annual_income_paise: int = Field(0, description="User's annual gross income in paise (from profile)")
    is_family_scope: bool = Field(False, description="True if coverage should include dependants")
    existing_life_cover_paise: int = Field(0, description="Current life insurance sum assured in paise")
    existing_health_cover_paise: int = Field(0, description="Current health insurance sum insured in paise")


# ── Registry ──────────────────────────────────────────────────────────────────

ToolFn = Callable[..., Coroutine[Any, Any, ToolResult]]

TOOL_REGISTRY: dict[str, tuple[ToolFn, type[BaseModel]]] = {
    "transaction_query": (transaction_query_run, TransactionQueryInput),
    "category_analysis": (category_analysis_run, CategoryAnalysisInput),
    "net_worth": (net_worth_run, NetWorthInput),
    "portfolio_value": (portfolio_value_run, PortfolioValueInput),
    "tax_summary": (tax_summary_run, TaxSummaryInput),
    "upcoming_expenses": (upcoming_expenses_run, UpcomingExpensesInput),
    # Phase 3
    "spending_trend": (spending_trend_run, SpendingTrendInput),
    "budget_comparison": (budget_comparison_run, BudgetComparisonInput),
    "goal_progress": (goal_progress_run, GoalProgressInput),
    # Phase 4 — risk domain
    "emergency_fund_months": (emergency_fund_months_run, EmergencyFundMonthsInput),
    "asset_concentration": (asset_concentration_run, AssetConcentrationInput),
    "debt_to_income": (debt_to_income_run, DebtToIncomeInput),
    "insurance_coverage_gap": (insurance_coverage_gap_run, InsuranceCoverageGapInput),
}


def build_langchain_tools(session: AsyncSession) -> list[StructuredTool]:
    """
    Bind the DB session into each tool and return LangChain StructuredTool objects
    suitable for passing to a LangGraph ToolNode.
    """
    tools = []
    for name, (fn, schema) in TOOL_REGISTRY.items():
        # Bind session via closure
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
