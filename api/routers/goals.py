"""
Goals router.

GET    /owners/{owner_id}/goals          — list goals (auth; self or admin)
POST   /owners/{owner_id}/goals          — create goal (auth; self or admin)
PATCH  /owners/{owner_id}/goals/{id}     — update goal (auth; self or admin)
DELETE /owners/{owner_id}/goals/{id}     — soft-delete via is_active=False (auth; self or admin)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import current_owner
from libs.schemas.db_models import FinancialGoal, Owner

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/owners/{owner_id}/goals", tags=["goals"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GoalOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    goal_name: str
    target_amount_paise: int
    current_amount_paise: int
    target_date: date | None
    category: str | None
    is_active: bool
    progress_pct: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateGoalRequest(BaseModel):
    goal_name: str = Field(min_length=1, max_length=256)
    target_amount_paise: int = Field(gt=0, description="Target in paise (int64, never float)")
    current_amount_paise: int = Field(default=0, ge=0)
    target_date: date | None = None
    category: str | None = Field(default=None, max_length=32)


class PatchGoalRequest(BaseModel):
    goal_name: str | None = Field(default=None, min_length=1, max_length=256)
    target_amount_paise: int | None = Field(default=None, gt=0)
    current_amount_paise: int | None = Field(default=None, ge=0)
    target_date: date | None = None
    category: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_access(requesting_owner: Owner, target_owner_id: uuid.UUID) -> None:
    if not requesting_owner.is_admin and requesting_owner.id != target_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _progress_pct(current: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return round(min(current / target * 100, 100.0), 2)


def _goal_out(goal: FinancialGoal) -> GoalOut:
    return GoalOut(
        id=goal.id,
        owner_id=goal.owner_id,
        goal_name=goal.goal_name,
        target_amount_paise=goal.target_amount_paise,
        current_amount_paise=goal.current_amount_paise,
        target_date=goal.target_date,
        category=goal.category,
        is_active=goal.is_active,
        progress_pct=_progress_pct(goal.current_amount_paise, goal.target_amount_paise),
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[GoalOut])
async def list_goals(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False,
) -> list[GoalOut]:
    _check_access(requesting_owner, owner_id)
    q = select(FinancialGoal).where(FinancialGoal.owner_id == owner_id)
    if not include_inactive:
        q = q.where(FinancialGoal.is_active.is_(True))
    q = q.order_by(FinancialGoal.target_date.nullslast(), FinancialGoal.goal_name)
    result = await session.execute(q)
    return [_goal_out(g) for g in result.scalars().all()]


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    owner_id: uuid.UUID,
    body: CreateGoalRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    _check_access(requesting_owner, owner_id)

    goal = FinancialGoal(
        owner_id=owner_id,
        goal_name=body.goal_name,
        target_amount_paise=body.target_amount_paise,
        current_amount_paise=body.current_amount_paise,
        target_date=body.target_date,
        category=body.category,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    log.info("goals.created", goal_id=str(goal.id), owner_id=str(owner_id))
    return _goal_out(goal)


@router.patch("/{goal_id}", response_model=GoalOut)
async def patch_goal(
    owner_id: uuid.UUID,
    goal_id: uuid.UUID,
    body: PatchGoalRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    _check_access(requesting_owner, owner_id)

    result = await session.execute(
        select(FinancialGoal).where(
            FinancialGoal.id == goal_id,
            FinancialGoal.owner_id == owner_id,
        )
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    if body.goal_name is not None:
        goal.goal_name = body.goal_name
    if body.target_amount_paise is not None:
        goal.target_amount_paise = body.target_amount_paise
    if body.current_amount_paise is not None:
        goal.current_amount_paise = body.current_amount_paise
    if body.target_date is not None:
        goal.target_date = body.target_date
    if body.category is not None:
        goal.category = body.category
    if body.is_active is not None:
        goal.is_active = body.is_active

    goal.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(goal)
    return _goal_out(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_goal(
    owner_id: uuid.UUID,
    goal_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> None:
    _check_access(requesting_owner, owner_id)

    result = await session.execute(
        select(FinancialGoal).where(
            FinancialGoal.id == goal_id,
            FinancialGoal.owner_id == owner_id,
        )
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    goal.is_active = False
    goal.updated_at = datetime.now(timezone.utc)
    await session.commit()
    log.info("goals.deactivated", goal_id=str(goal_id))
