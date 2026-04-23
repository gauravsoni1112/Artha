"""
Net Worth router.

GET /owners/{owner_id}/net-worth  — totals, monthly history, and assets-by-category
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import check_owner_access, current_owner
from libs.schemas.db_models import Holding, Owner, Transaction

router = APIRouter(prefix="/owners/{owner_id}/net-worth", tags=["net-worth"])


class MonthlyNetWorth(BaseModel):
    month: str           # "YYYY-MM"
    net_worth_paise: int  # cumulative tx balance + current holdings value (constant offset)
    change_paise: int    # net cash flow for this month
    change_pct: float | None


class AssetCategory(BaseModel):
    label: str
    value_paise: int
    pct: float
    delta_paise: int     # always 0 — no historical holdings prices available


class NetWorthOut(BaseModel):
    total_assets_paise: int
    total_liabilities_paise: int
    net_worth_paise: int
    history: list[MonthlyNetWorth]
    assets_by_category: list[AssetCategory]


def _net_flow_expr():
    return func.sum(
        case(
            (Transaction.transaction_type == "CREDIT", Transaction.amount_paise),
            else_=-Transaction.amount_paise,
        )
    )


@router.get("", response_model=NetWorthOut)
async def get_net_worth(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> NetWorthOut:
    check_owner_access(requesting_owner, owner_id)

    # ── 1. Holdings current value (needed for both history offset and totals) ──
    holdings_result = await session.execute(
        select(Holding.asset_class, func.sum(Holding.current_value_paise).label("total_paise"))
        .where(Holding.owner_id == owner_id, Holding.current_value_paise.isnot(None))
        .group_by(Holding.asset_class)
    )
    holdings_by_class: dict[str, int] = {
        row.asset_class: int(row.total_paise) for row in holdings_result
    }
    total_holdings_paise = sum(holdings_by_class.values())

    # ── 2. Monthly net cash flow from transactions ────────────────────────────
    # Use literal_column for the format string so PostgreSQL sees one expression
    # in both SELECT and GROUP BY (asyncpg parameterizes strings separately otherwise).
    _month_expr = func.to_char(Transaction.transaction_date, literal_column("'YYYY-MM'"))
    monthly_result = await session.execute(
        select(
            _month_expr.label("month"),
            _net_flow_expr().label("net_flow_paise"),
        )
        .where(Transaction.owner_id == owner_id)
        .group_by(_month_expr)
        .order_by(_month_expr)
    )
    monthly_rows = monthly_result.all()

    # Cumulative tx balance per month + holdings as constant offset so the final
    # month matches the headline net_worth_paise. Holdings history isn't tracked,
    # so we approximate by spreading the current value across all months.
    history: list[MonthlyNetWorth] = []
    cumulative_tx = 0
    for row in monthly_rows:
        prev_tx = cumulative_tx
        cumulative_tx += int(row.net_flow_paise)
        prev_net_worth = prev_tx + total_holdings_paise
        change_pct = (int(row.net_flow_paise) / prev_net_worth * 100) if prev_net_worth != 0 else None
        history.append(MonthlyNetWorth(
            month=row.month,
            net_worth_paise=cumulative_tx + total_holdings_paise,
            change_paise=int(row.net_flow_paise),
            change_pct=change_pct,
        ))

    # ── 3. Current transaction-based balances per account ────────────────────
    acct_balance_result = await session.execute(
        select(
            Transaction.account_id,
            _net_flow_expr().label("balance_paise"),
        )
        .where(Transaction.owner_id == owner_id)
        .group_by(Transaction.account_id)
    )
    acct_balances = acct_balance_result.all()

    total_assets_from_accts = sum(int(r.balance_paise) for r in acct_balances if r.balance_paise > 0)
    total_liabilities_paise = abs(sum(int(r.balance_paise) for r in acct_balances if r.balance_paise < 0))

    total_assets_paise = total_assets_from_accts + total_holdings_paise
    net_worth_paise = total_assets_paise - total_liabilities_paise

    # ── 4. Assets by category ────────────────────────────────────────────────
    assets_by_category: list[AssetCategory] = []
    if total_assets_paise > 0:
        if total_assets_from_accts > 0:
            assets_by_category.append(AssetCategory(
                label="Bank Accounts",
                value_paise=total_assets_from_accts,
                pct=round(total_assets_from_accts / total_assets_paise * 100, 2),
                delta_paise=0,
            ))
        for asset_class, value in sorted(holdings_by_class.items()):
            assets_by_category.append(AssetCategory(
                label=asset_class.replace("_", " ").title(),
                value_paise=value,
                pct=round(value / total_assets_paise * 100, 2),
                delta_paise=0,
            ))

    return NetWorthOut(
        total_assets_paise=total_assets_paise,
        total_liabilities_paise=total_liabilities_paise,
        net_worth_paise=net_worth_paise,
        history=history,
        assets_by_category=assets_by_category,
    )
