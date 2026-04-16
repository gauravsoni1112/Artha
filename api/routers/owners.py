"""
Owners router.

GET  /owners              — list all owners (auth required)
GET  /owners/{id}         — single owner (auth required)
POST /owners              — create owner (admin required)
PATCH /owners/{id}        — update name / is_admin (admin required)
POST /owners/{id}/pin     — set / reset PIN (admin required)
GET  /owners/{id}/family  — list family members for this owner's family
POST /owners/{id}/family  — add a member to this owner's family (admin required)
DELETE /owners/{id}/family/{member_id} — remove member (admin required)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.deps import current_owner, hash_pin, require_admin
from libs.schemas.db_models import FamilyMembership, Owner

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/owners", tags=["owners"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OwnerOut(BaseModel):
    id: uuid.UUID
    name: str
    is_admin: bool
    has_pin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateOwnerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    is_admin: bool = False
    pin: str | None = Field(default=None, min_length=4, max_length=64)


class PatchOwnerRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    is_admin: bool | None = None


class SetPinRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=64)


class FamilyMemberOut(BaseModel):
    owner_id: uuid.UUID
    name: str
    role: str
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AddFamilyMemberRequest(BaseModel):
    owner_id: uuid.UUID
    role: str = Field(pattern="^(PRIMARY|SPOUSE|DEPENDENT)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owner_out(owner: Owner) -> OwnerOut:
    return OwnerOut(
        id=owner.id,
        name=owner.name,
        is_admin=owner.is_admin,
        has_pin=owner.pin_hash is not None,
        created_at=owner.created_at,
        updated_at=owner.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[OwnerOut])
async def list_owners(
    _owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> list[OwnerOut]:
    result = await session.execute(select(Owner).order_by(Owner.name))
    return [_owner_out(o) for o in result.scalars().all()]


@router.get("/{owner_id}", response_model=OwnerOut)
async def get_owner(
    owner_id: uuid.UUID,
    _owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> OwnerOut:
    result = await session.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return _owner_out(owner)


@router.post("", response_model=OwnerOut, status_code=status.HTTP_201_CREATED)
async def create_owner(
    body: CreateOwnerRequest,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> OwnerOut:
    owner = Owner(
        name=body.name,
        is_admin=body.is_admin,
        pin_hash=hash_pin(body.pin) if body.pin else None,
    )
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    log.info("owners.created", owner_id=str(owner.id), name=owner.name)
    return _owner_out(owner)


@router.patch("/{owner_id}", response_model=OwnerOut)
async def patch_owner(
    owner_id: uuid.UUID,
    body: PatchOwnerRequest,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> OwnerOut:
    result = await session.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    if body.name is not None:
        owner.name = body.name
    if body.is_admin is not None:
        owner.is_admin = body.is_admin

    owner.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(owner)
    return _owner_out(owner)


@router.post("/{owner_id}/pin", status_code=status.HTTP_204_NO_CONTENT)
async def set_pin(
    owner_id: uuid.UUID,
    body: SetPinRequest,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    owner.pin_hash = hash_pin(body.pin)
    owner.updated_at = datetime.now(timezone.utc)
    await session.commit()
    log.info("owners.pin_set", owner_id=str(owner_id))


@router.get("/{owner_id}/family", response_model=list[FamilyMemberOut])
async def list_family_members(
    owner_id: uuid.UUID,
    _owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> list[FamilyMemberOut]:
    result = await session.execute(
        select(FamilyMembership, Owner)
        .join(Owner, Owner.id == FamilyMembership.owner_id)
        .where(FamilyMembership.family_id == owner_id)
        .order_by(FamilyMembership.created_at)
    )
    rows = result.all()
    return [
        FamilyMemberOut(
            owner_id=fm.owner_id,
            name=o.name,
            role=fm.role,
            is_admin=o.is_admin,
            created_at=fm.created_at,
        )
        for fm, o in rows
    ]


@router.post("/{owner_id}/family", response_model=FamilyMemberOut, status_code=status.HTTP_201_CREATED)
async def add_family_member(
    owner_id: uuid.UUID,
    body: AddFamilyMemberRequest,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> FamilyMemberOut:
    # Verify the target owner exists
    member_result = await session.execute(select(Owner).where(Owner.id == body.owner_id))
    member = member_result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member owner not found")

    fm = FamilyMembership(family_id=owner_id, owner_id=body.owner_id, role=body.role)
    session.add(fm)
    try:
        await session.commit()
        await session.refresh(fm)
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Member already in family")

    return FamilyMemberOut(
        owner_id=fm.owner_id,
        name=member.name,
        role=fm.role,
        is_admin=member.is_admin,
        created_at=fm.created_at,
    )


@router.delete("/{owner_id}/family/{member_owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_family_member(
    owner_id: uuid.UUID,
    member_owner_id: uuid.UUID,
    _admin: Annotated[Owner, Depends(require_admin)],
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(
        select(FamilyMembership).where(
            FamilyMembership.family_id == owner_id,
            FamilyMembership.owner_id == member_owner_id,
        )
    )
    fm = result.scalar_one_or_none()
    if fm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family member not found")
    await session.delete(fm)
    await session.commit()
