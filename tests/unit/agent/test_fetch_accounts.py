"""
Golden-input tests for tools/fetch_accounts.py.

All DB interactions are mocked — no Docker required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent.tools.fetch_accounts import run
from services.agent.tools.base import ToolResult


def _make_account(
    account_type: str = "BANK",
    institution: str = "HDFC",
    nickname: str | None = None,
    is_active: bool = True,
):
    account = MagicMock()
    account.id = uuid.uuid4()
    account.account_type = account_type
    account.institution = institution
    account.nickname = nickname
    account.is_active = is_active
    account.created_at = datetime.now(timezone.utc)
    return account


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


def _patch_scalars(session, accounts):
    scalars_result = MagicMock()
    scalars_result.all.return_value = accounts
    session.scalars = AsyncMock(return_value=scalars_result)
    return session


def _patch_scalar_count(session, count):
    session.scalar = AsyncMock(return_value=count)
    return session


@pytest.mark.asyncio
async def test_fetch_accounts_returns_tool_result(mock_session):
    owner_id = str(uuid.uuid4())
    accounts = [_make_account()]
    _patch_scalars(mock_session, accounts)
    _patch_scalar_count(mock_session, 5)

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result, ToolResult)
    assert result.tool_name == "fetch_accounts"


@pytest.mark.asyncio
async def test_fetch_accounts_data_freshness_present(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])
    _patch_scalar_count(mock_session, 0)

    result = await run(session=mock_session, owner_id=owner_id)

    assert isinstance(result.data_freshness, datetime)
    assert result.data_freshness.tzinfo is not None


@pytest.mark.asyncio
async def test_fetch_accounts_includes_all_account_details(mock_session):
    owner_id = str(uuid.uuid4())
    account = _make_account(
        account_type="CREDIT_CARD",
        institution="ICICI",
        nickname="My Credit Card",
        is_active=True,
    )
    _patch_scalars(mock_session, [account])
    _patch_scalar_count(mock_session, 3)

    result = await run(session=mock_session, owner_id=owner_id)

    accounts = result.data["accounts"]
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc["type"] == "CREDIT_CARD"
    assert acc["institution"] == "ICICI"
    assert acc["nickname"] == "My Credit Card"
    assert acc["is_active"] is True
    assert acc["transaction_count"] == 3


@pytest.mark.asyncio
async def test_fetch_accounts_uses_nickname_or_fallback(mock_session):
    owner_id = str(uuid.uuid4())
    # Account with nickname
    acc_with_nick = _make_account(
        account_type="BANK",
        institution="HDFC",
        nickname="Savings Account",
    )
    # Account without nickname should use fallback
    acc_no_nick = _make_account(
        account_type="BANK",
        institution="ICICI",
        nickname=None,
    )
    _patch_scalars(mock_session, [acc_with_nick, acc_no_nick])
    _patch_scalar_count(mock_session, 2)

    result = await run(session=mock_session, owner_id=owner_id)

    accounts = result.data["accounts"]
    assert accounts[0]["nickname"] == "Savings Account"
    assert accounts[1]["nickname"] == "ICICI BANK"


@pytest.mark.asyncio
async def test_fetch_accounts_empty_returns_zero_count(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])
    _patch_scalar_count(mock_session, 0)

    result = await run(session=mock_session, owner_id=owner_id)

    assert result.data["count"] == 0
    assert result.data["accounts"] == []


@pytest.mark.asyncio
async def test_fetch_accounts_query_params_echoed(mock_session):
    owner_id = str(uuid.uuid4())
    _patch_scalars(mock_session, [])
    _patch_scalar_count(mock_session, 0)

    result = await run(
        session=mock_session,
        owner_id=owner_id,
        account_type="BANK",
    )

    assert result.query_params["owner_id"] == owner_id
    assert result.query_params["account_type"] == "BANK"


@pytest.mark.asyncio
async def test_fetch_accounts_to_llm_str_is_valid_json(mock_session):
    import json

    owner_id = str(uuid.uuid4())
    accounts = [_make_account()]
    _patch_scalars(mock_session, accounts)
    _patch_scalar_count(mock_session, 1)

    result = await run(session=mock_session, owner_id=owner_id)
    payload = json.loads(result.to_llm_str())

    assert "data_freshness" in payload
    assert "data" in payload
    assert "tool_name" in payload
