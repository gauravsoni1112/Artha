"""
User profile router.

GET   /owners/{owner_id}/profile   — fetch profile (auth; self or admin)
PATCH /owners/{owner_id}/profile   — update profile (auth; self or admin)
POST  /owners/{owner_id}/profile   — create profile if missing (auth; self or admin)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import get_session
from api.deps import current_owner
from libs.schemas.db_models import Owner, UserProfile, UserProfileScope

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/owners/{owner_id}/profile", tags=["profile"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProfileScopeOut(BaseModel):
    owner_id: uuid.UUID
    scope: str  # PRIMARY | SPOUSE | DEPENDENT


class ProfileOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    risk_appetite: str
    age: int | None
    is_family_scope: bool
    total_monthly_income_paise: int
    income_sources_json: list[Any]
    emis_json: list[Any]
    preferences: dict[str, Any]
    scopes: list[ProfileScopeOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatchProfileRequest(BaseModel):
    risk_appetite: str | None = Field(default=None, pattern="^(conservative|moderate|aggressive)$")
    age: int | None = Field(default=None, ge=0, le=120)
    is_family_scope: bool | None = None
    total_monthly_income_paise: int | None = Field(default=None, ge=0)
    income_sources_json: list[Any] | None = None
    emis_json: list[Any] | None = None
    preferences: dict[str, Any] | None = None


class CreateProfileRequest(BaseModel):
    risk_appetite: str = Field(default="moderate", pattern="^(conservative|moderate|aggressive)$")
    age: int | None = Field(default=None, ge=0, le=120)
    total_monthly_income_paise: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_access(requesting_owner: Owner, target_owner_id: uuid.UUID) -> None:
    if not requesting_owner.is_admin and requesting_owner.id != target_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _load_profile_with_scopes(
    session: AsyncSession, owner_id: uuid.UUID
) -> UserProfile | None:
    result = await session.execute(
        select(UserProfile)
        .options(selectinload(UserProfile.scopes))
        .where(UserProfile.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


def _profile_out(profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        owner_id=profile.owner_id,
        risk_appetite=profile.risk_appetite,
        age=profile.age,
        is_family_scope=profile.is_family_scope,
        total_monthly_income_paise=profile.total_monthly_income_paise,
        income_sources_json=profile.income_sources_json,
        emis_json=profile.emis_json,
        preferences=profile.preferences,
        scopes=[ProfileScopeOut(owner_id=s.owner_id, scope=s.scope) for s in (profile.scopes or [])],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProfileOut)
async def get_profile(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    _check_access(requesting_owner, owner_id)
    profile = await _load_profile_with_scopes(session, owner_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return _profile_out(profile)


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    owner_id: uuid.UUID,
    body: CreateProfileRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    _check_access(requesting_owner, owner_id)

    existing = await _load_profile_with_scopes(session, owner_id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile already exists")

    profile = UserProfile(
        owner_id=owner_id,
        risk_appetite=body.risk_appetite,
        age=body.age,
        total_monthly_income_paise=body.total_monthly_income_paise,
        preferences={},
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    profile.scopes = []
    log.info("profile.created", owner_id=str(owner_id))
    return _profile_out(profile)


@router.patch("", response_model=ProfileOut)
async def patch_profile(
    owner_id: uuid.UUID,
    body: PatchProfileRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    _check_access(requesting_owner, owner_id)
    profile = await _load_profile_with_scopes(session, owner_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found — POST to create")

    if body.risk_appetite is not None:
        profile.risk_appetite = body.risk_appetite
    if body.age is not None:
        profile.age = body.age
    if body.is_family_scope is not None:
        profile.is_family_scope = body.is_family_scope
    if body.total_monthly_income_paise is not None:
        profile.total_monthly_income_paise = body.total_monthly_income_paise
    if body.income_sources_json is not None:
        profile.income_sources_json = body.income_sources_json
    if body.emis_json is not None:
        profile.emis_json = body.emis_json
    if body.preferences is not None:
        # Merge — don't wipe keys not sent
        merged = dict(profile.preferences or {})
        merged.update(body.preferences)
        profile.preferences = merged

    profile.updated_at = datetime.now(timezone.utc)
    await session.commit()
    # Reload with scopes eagerly after commit
    return _profile_out(await _load_profile_with_scopes(session, owner_id))
