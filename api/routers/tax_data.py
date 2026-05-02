"""
Tax Data router.

GET /owners/{owner_id}/tax-data  — list ITR records per fiscal year
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import check_owner_access, current_owner
from libs.schemas.db_models import Owner, TaxData

router = APIRouter(prefix="/owners/{owner_id}/tax-data", tags=["tax"])


class TaxDataOut(BaseModel):
    id: uuid.UUID
    fiscal_year: str
    gross_income_paise: int | None
    taxable_income_paise: int | None
    tax_paid_paise: int | None
    tds_paise: int | None
    itr_filed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[TaxDataOut])
async def list_tax_data(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> list[TaxDataOut]:
    check_owner_access(requesting_owner, owner_id)
    result = await session.execute(
        select(TaxData)
        .where(TaxData.owner_id == owner_id)
        .order_by(TaxData.fiscal_year.desc())
    )
    return result.scalars().all()
