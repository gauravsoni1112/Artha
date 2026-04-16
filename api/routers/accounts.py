"""
Accounts router.

GET    /owners/{owner_id}/accounts          — list accounts (auth required)
POST   /owners/{owner_id}/accounts          — create account (auth; must be self or admin)
PATCH  /owners/{owner_id}/accounts/{id}     — update account (auth; must be self or admin)
DELETE /owners/{owner_id}/accounts/{id}     — soft-delete via is_active=False (auth; must be self or admin)
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
from api.deps import current_owner
from libs.schemas.db_models import Account, Owner

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/owners/{owner_id}/accounts", tags=["accounts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AccountOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    account_type: str
    institution: str
    nickname: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateAccountRequest(BaseModel):
    account_type: str = Field(min_length=1, max_length=32)
    institution: str = Field(min_length=1, max_length=256)
    nickname: str | None = Field(default=None, max_length=128)
    account_number: str | None = Field(default=None, description="Stored as SHA-256 hash")


class PatchAccountRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=128)
    institution: str | None = Field(default=None, min_length=1, max_length=256)
    account_type: str | None = Field(default=None, min_length=1, max_length=32)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_access(requesting_owner: Owner, target_owner_id: uuid.UUID) -> None:
    """Allow if caller is admin OR is accessing their own accounts."""
    if not requesting_owner.is_admin and requesting_owner.id != target_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _hash_account_number(account_number: str) -> str:
    import hashlib
    return hashlib.sha256(account_number.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    owner_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
    include_inactive: bool = False,
) -> list[AccountOut]:
    _check_access(requesting_owner, owner_id)
    q = select(Account).where(Account.owner_id == owner_id)
    if not include_inactive:
        q = q.where(Account.is_active.is_(True))
    q = q.order_by(Account.institution, Account.account_type)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    owner_id: uuid.UUID,
    body: CreateAccountRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> AccountOut:
    _check_access(requesting_owner, owner_id)

    account = Account(
        owner_id=owner_id,
        account_type=body.account_type,
        institution=body.institution,
        nickname=body.nickname,
        account_number_hash=_hash_account_number(body.account_number) if body.account_number else None,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    log.info("accounts.created", account_id=str(account.id), owner_id=str(owner_id))
    return account


@router.patch("/{account_id}", response_model=AccountOut)
async def patch_account(
    owner_id: uuid.UUID,
    account_id: uuid.UUID,
    body: PatchAccountRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> AccountOut:
    _check_access(requesting_owner, owner_id)

    result = await session.execute(
        select(Account).where(Account.id == account_id, Account.owner_id == owner_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if body.nickname is not None:
        account.nickname = body.nickname
    if body.institution is not None:
        account.institution = body.institution
    if body.account_type is not None:
        account.account_type = body.account_type
    if body.is_active is not None:
        account.is_active = body.is_active

    await session.commit()
    await session.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_account(
    owner_id: uuid.UUID,
    account_id: uuid.UUID,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> None:
    _check_access(requesting_owner, owner_id)

    result = await session.execute(
        select(Account).where(Account.id == account_id, Account.owner_id == owner_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account.is_active = False
    await session.commit()
    log.info("accounts.deactivated", account_id=str(account_id))
