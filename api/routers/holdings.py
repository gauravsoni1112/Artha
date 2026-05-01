"""
Holdings router.

GET /owners/{owner_id}/holdings  — list all holdings with computed P&L (auth required)
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import check_owner_access, current_owner
from libs.schemas.db_models import Holding, Owner

router = APIRouter(prefix="/owners/{owner_id}/holdings", tags=["holdings"])


class HoldingCreate(BaseModel):
    asset_class: str
    instrument_name: str
    isin: str | None = None
    units: float | None = None
    nav_paise: int | None = None
    purchase_price_paise: int | None = None
    current_value_paise: int | None = None
    valuation_date: date | None = None
    metadata: dict | None = None


class HoldingOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID | None
    asset_class: str
    instrument_name: str
    isin: str | None
    units: float | None
    nav_paise: int | None
    purchase_price_paise: int | None
    current_value_paise: int | None
    valuation_date: date | None
    avg_cost_paise: int | None     # round(purchase_price_paise / units)
    pl_paise: int | None           # current_value_paise - purchase_price_paise
    pl_pct: float | None           # pl_paise / purchase_price_paise * 100
    xirr: float | None = None      # no price history table yet
    day_change_pct: float | None = None  # no price history table yet
    metadata: dict | None = None


def _to_out(h: Holding) -> HoldingOut:
    units = float(h.units) if h.units is not None else None

    avg_cost: int | None = None
    if h.purchase_price_paise is not None and units and units > 0:
        avg_cost = round(h.purchase_price_paise / units)

    pl_paise: int | None = None
    pl_pct: float | None = None
    if h.current_value_paise is not None and h.purchase_price_paise is not None:
        pl_paise = h.current_value_paise - h.purchase_price_paise
        if h.purchase_price_paise > 0:
            pl_pct = pl_paise / h.purchase_price_paise * 100

    return HoldingOut(
        id=h.id,
        account_id=h.account_id,
        asset_class=h.asset_class,
        instrument_name=h.instrument_name,
        isin=h.isin,
        units=units,
        nav_paise=h.nav_paise,
        purchase_price_paise=h.purchase_price_paise,
        current_value_paise=h.current_value_paise,
        valuation_date=h.valuation_date,
        avg_cost_paise=avg_cost,
        pl_paise=pl_paise,
        pl_pct=pl_pct,
        metadata=h.metadata_,
    )


@router.post("", response_model=HoldingOut, status_code=201)
async def create_holding(
    owner_id: uuid.UUID,
    body: HoldingCreate,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> HoldingOut:
    check_owner_access(requesting_owner, owner_id)
    holding = Holding(
        owner_id=owner_id,
        asset_class=body.asset_class,
        instrument_name=body.instrument_name,
        isin=body.isin,
        units=body.units,
        nav_paise=body.nav_paise,
        purchase_price_paise=body.purchase_price_paise,
        current_value_paise=body.current_value_paise,
        valuation_date=body.valuation_date,
        metadata_=body.metadata,
    )
    session.add(holding)
    await session.commit()
    await session.refresh(holding)
    return _to_out(holding)


@router.get("", response_model=list[HoldingOut])
async def list_holdings(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> list[HoldingOut]:
    check_owner_access(requesting_owner, owner_id)
    result = await session.execute(
        select(Holding)
        .where(Holding.owner_id == owner_id)
        .order_by(Holding.asset_class, Holding.instrument_name)
    )
    return [_to_out(h) for h in result.scalars().all()]
