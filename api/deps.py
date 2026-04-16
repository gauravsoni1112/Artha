"""
FastAPI dependencies for authentication and authorisation.

Token format (stateless, no DB lookup per request):
    <base64url(json_payload)>.<base64url(hmac_sha256_signature)>

Payload: {"owner_id": "<uuid>", "exp": <unix_ts_int>}
Secret:  ARTHA_AUTH_SECRET env var (default: "dev-secret-change-me")

PIN hashing:  hashlib.scrypt — stdlib, no extra deps.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from libs.schemas.db_models import Owner

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SECRET: str = os.getenv("ARTHA_AUTH_SECRET", "dev-secret-change-me")
_TOKEN_TTL_SECONDS: int = int(os.getenv("ARTHA_TOKEN_TTL", str(8 * 3600)))  # 8 hours

# scrypt params — OWASP recommended minimums
_SCRYPT_N = 2**14  # CPU/memory cost (16 MB; fits OpenSSL's default maxmem)
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


# ---------------------------------------------------------------------------
# PIN hashing helpers (used by auth router and owners router)
# ---------------------------------------------------------------------------


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    """Return "<hex_salt>:<hex_hash>" using scrypt."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.scrypt(pin.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN)
    return f"{salt.hex()}:{dk.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Return True iff pin matches the stored '<salt_hex>:<hash_hex>'."""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.scrypt(pin.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token helpers (used by auth router)
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    # Add padding back
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def create_token(owner_id: uuid.UUID) -> str:
    """Sign and return a short-lived token for the given owner."""
    payload = json.dumps({"owner_id": str(owner_id), "exp": int(time.time()) + _TOKEN_TTL_SECONDS}).encode()
    payload_b64 = _b64url_encode(payload)
    sig = hmac.new(_SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def _decode_token(token: str) -> dict:
    """Return decoded payload dict or raise HTTPException 401."""
    try:
        payload_b64, sig_b64 = token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")

    expected_sig = hmac.new(_SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest()
    provided_sig = _b64url_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token payload")

    if payload.get("exp", 0) < time.time():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def current_owner(
    x_artha_token: Annotated[str | None, Header(alias="X-Artha-Token")] = None,
    session: AsyncSession = Depends(get_session),
) -> Owner:
    """Resolve and return the authenticated Owner.  Raises 401 if missing/invalid."""
    if not x_artha_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Artha-Token header")

    payload = _decode_token(x_artha_token)

    try:
        owner_id = uuid.UUID(payload["owner_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid owner_id in token")

    result = await session.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Owner not found")

    return owner


async def require_admin(owner: Annotated[Owner, Depends(current_owner)]) -> Owner:
    """Like current_owner but additionally requires is_admin=True.  Raises 403 otherwise."""
    if not owner.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return owner
