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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.agent.tools.base import ToolResult
from services.agent.tools.fetch_accounts import run as fetch_accounts_run
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
# Pure-math tools (session-less, prevent LLM from doing arithmetic inline)
from services.agent.tools.calculate import (
    run_convert as convert_amount_run,
    run_percentage as calculate_percentage_run,
    run_growth as calculate_growth_run,
    run_compound_interest as calculate_compound_interest_run,
)


# ── Input schemas (used by LangGraph for JSON schema extraction) ───────────────

class FetchAccountsInput(BaseModel):
    account_type: str | None = Field(
        None,
        description=(
            "Filter by account type. Exact values: SAVINGS, CHECKING, CREDIT_CARD, DEMAT, MF_FOLIO, PPF, NPS, FD, OTHER. "
            "Use the shorthand INVESTMENT to fetch all investment accounts (DEMAT, MF_FOLIO, PPF, NPS, FD)."
        ),
    )


class TransactionQueryInput(BaseModel):
    start_date: str | None = Field(None, description="Start date YYYY-MM-DD (inclusive)")
    end_date: str | None = Field(None, description="End date YYYY-MM-DD (inclusive)")
    category: str | None = Field(None, description="Transaction category filter e.g. GROCERIES")
    account_id: str | None = Field(None, description="Filter by specific account UUID")
    limit: int = Field(50, description="Max rows to return")


class CategoryAnalysisInput(BaseModel):
    start_date: str | None = Field(None, description="Start date YYYY-MM-DD")
    end_date: str | None = Field(None, description="End date YYYY-MM-DD")
    fiscal_year: str | None = Field(None, description="Fiscal year e.g. 2024-25")


class NetWorthInput(BaseModel):
    pass


class PortfolioValueInput(BaseModel):
    asset_class: str | None = Field(None, description="Filter by asset class e.g. MUTUAL_FUND, EQUITY")


class TaxSummaryInput(BaseModel):
    fiscal_year: str | None = Field(None, description="Fiscal year e.g. 2024-25; omit for all years")


class UpcomingExpensesInput(BaseModel):
    lookahead_days: int = Field(30, description="Days ahead to predict recurring expenses")


class SpendingTrendInput(BaseModel):
    category: str | None = Field(None, description="Category to trend e.g. GROCERIES; omit for all")
    months: int = Field(6, description="Number of months to include (default 6)")


class BudgetComparisonInput(BaseModel):
    start_date: str | None = Field(None, description="Start date YYYY-MM-DD")
    end_date: str | None = Field(None, description="End date YYYY-MM-DD")
    fiscal_year: str | None = Field(None, description="Fiscal year e.g. 2024-25")


class GoalProgressInput(BaseModel):
    goal_name: str | None = Field(None, description="Partial goal name filter; omit for all goals")


class EmergencyFundMonthsInput(BaseModel):
    expense_months: int = Field(3, description="Number of recent months used to compute avg expense (default 3)")


class AssetConcentrationInput(BaseModel):
    concentration_threshold_pct: float = Field(
        40.0, description="Flag asset classes above this % of total portfolio (default 40)"
    )


class DebtToIncomeInput(BaseModel):
    months: int = Field(3, description="Number of recent months to average over (default 3)")


class InsuranceCoverageGapInput(BaseModel):
    annual_income_paise: int = Field(0, description="User's annual gross income in paise (from profile)")
    is_family_scope: bool = Field(False, description="True if coverage should include dependants")
    existing_life_cover_paise: int = Field(0, description="Current life insurance sum assured in paise")
    existing_health_cover_paise: int = Field(0, description="Current health insurance sum insured in paise")


class ConvertAmountInput(BaseModel):
    amount: float = Field(description="Numeric value to convert, e.g. 5.0 for '5 lakhs'")
    from_unit: str = Field(description="Source denomination: 'paise', 'rupee', 'lakh', or 'crore'")
    to_unit: str = Field(description="Target denomination: 'paise', 'rupee', 'lakh', or 'crore'")


class CalculatePercentageInput(BaseModel):
    base_paise: int = Field(description="Base amount in paise, e.g. 20000000 for ₹2,00,000")
    percent: float = Field(description="Percentage to compute, e.g. 15.5 for 15.5%")


class CalculateGrowthInput(BaseModel):
    from_paise: int = Field(description="Starting amount in paise")
    to_paise: int = Field(description="Ending amount in paise")


class CalculateCompoundInterestInput(BaseModel):
    principal_paise: int = Field(description="Principal amount in paise")
    annual_rate_pct: float = Field(description="Annual interest rate in percent, e.g. 7.5")
    years: float = Field(description="Investment horizon in years, e.g. 3.5 for 3.5 years")
    compounding_frequency: int = Field(
        12, description="Compoundings per year: 1=annual, 4=quarterly, 12=monthly, 365=daily"
    )


# ── Registry ──────────────────────────────────────────────────────────────────

ToolFn = Callable[..., Coroutine[Any, Any, ToolResult]]

TOOL_REGISTRY: dict[str, tuple[ToolFn, type[BaseModel]]] = {
    "fetch_accounts": (fetch_accounts_run, FetchAccountsInput),
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
    # Pure-math tools — the LLM must use these instead of computing inline
    "convert_amount": (convert_amount_run, ConvertAmountInput),
    "calculate_percentage": (calculate_percentage_run, CalculatePercentageInput),
    "calculate_growth": (calculate_growth_run, CalculateGrowthInput),
    "calculate_compound_interest": (calculate_compound_interest_run, CalculateCompoundInterestInput),
}


def build_langchain_tools(session_factory: async_sessionmaker, owner_id: str) -> list[StructuredTool]:
    """
    Bind the DB session factory and authenticated owner_id into each tool.

    - Each invocation opens its own AsyncSession (no shared-session corruption).
    - owner_id is bound server-side: any value the LLM passes is discarded and
      replaced with the authenticated owner's UUID, preventing prompt-injection
      from causing cross-tenant data access.
    """
    tools = []
    for name, (fn, schema) in TOOL_REGISTRY.items():
        async def _bound(session_factory=session_factory, fn=fn, bound_owner_id=owner_id, **kwargs):
            kwargs.pop("owner_id", None)  # discard any LLM-supplied value
            async with session_factory() as session:
                return (await fn(session=session, owner_id=bound_owner_id, **kwargs)).to_llm_str()

        tools.append(
            StructuredTool(
                name=name,
                description=fn.__doc__ or name,
                args_schema=schema,
                coroutine=_bound,
            )
        )
    return tools
