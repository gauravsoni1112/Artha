"""
Authentication router.

POST /auth/login  — verify owner_id + PIN, return signed token
POST /auth/logout — stateless; client discards token (returns 200 for UX)
GET  /auth/me     — return current owner profile from token
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from api.database import get_session
from api.deps import create_token, current_owner, verify_pin
from libs.schemas.db_models import Owner

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    owner_id: uuid.UUID
    pin: str = Field(min_length=4, max_length=64)


class TokenResponse(BaseModel):
    token: str
    owner_id: uuid.UUID
    name: str
    is_admin: bool


class MeResponse(BaseModel):
    owner_id: uuid.UUID
    name: str
    is_admin: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Verify PIN and return a signed auth token."""
    result = await session.execute(select(Owner).where(Owner.id == body.owner_id))
    owner = result.scalar_one_or_none()

    # Constant-time-ish: always call verify_pin to avoid timing oracle
    stored_hash = owner.pin_hash if owner else "00" * 17 + ":00" * 17
    if owner is None or not verify_pin(body.pin, stored_hash):
        log.warning("auth.login_failed", owner_id=str(body.owner_id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid owner_id or PIN",
        )

    token = create_token(owner.id)
    log.info("auth.login_success", owner_id=str(owner.id))
    return TokenResponse(token=token, owner_id=owner.id, name=owner.name, is_admin=owner.is_admin)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout() -> dict:
    """Stateless logout — client discards the token."""
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(owner: Annotated[Owner, Depends(current_owner)]) -> MeResponse:
    """Return the authenticated owner's basic info."""
    return MeResponse(owner_id=owner.id, name=owner.name, is_admin=owner.is_admin)
