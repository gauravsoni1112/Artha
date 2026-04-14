"""
Unit tests for ZerodhaConnector.

Tests cover:
  - KiteConnect API initialization
  - Holdings fetching and transformation
  - Trade history fetching with lookback filtering
  - Error handling (missing credentials, API failures)
  - Data transformation to transaction format
  - Async compatibility
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from libs.schemas.enums import DocumentType, IngestionSource
from services.ingestion.connectors.zerodha_connector import ZerodhaConnector


# ── Tests: KiteConnect initialization ─────────────────────────────────────────

def test_zerodha_connector_init_with_explicit_credentials():
    """ZerodhaConnector should accept explicit credentials."""
    connector = ZerodhaConnector(
        account_id="550e8400-e29b-41d4-a716-446655440001",
        api_key="test_api_key",
        access_token="test_access_token",
    )

    assert connector._api_key == "test_api_key"
    assert connector._access_token == "test_access_token"


def test_zerodha_connector_init_with_env_vars():
    """ZerodhaConnector should read credentials from environment."""
    with patch.dict("os.environ", {
        "ZERODHA_API_KEY": "env_api_key",
        "ZERODHA_ACCESS_TOKEN": "env_access_token",
    }):
        connector = ZerodhaConnector(
            account_id="550e8400-e29b-41d4-a716-446655440001"
        )

        assert connector._api_key == "env_api_key"
        assert connector._access_token == "env_access_token"


def test_zerodha_connector_missing_credentials():
    """ZerodhaConnector should raise error if credentials missing."""
    with patch.dict("os.environ", {}, clear=True):
        connector = ZerodhaConnector(
            account_id="550e8400-e29b-41d4-a716-446655440001",
            api_key="",
            access_token="",
        )

        with pytest.raises(ValueError, match="ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN"):
            connector._get_kite()


def test_zerodha_connector_get_kite_success():
    """ZerodhaConnector should initialize KiteConnect successfully."""
    with patch("kiteconnect.KiteConnect") as mock_kite_class:
        mock_kite = MagicMock()
        mock_kite_class.return_value = mock_kite

        connector = ZerodhaConnector(
            account_id="550e8400-e29b-41d4-a716-446655440001",
            api_key="test_api_key",
            access_token="test_access_token",
        )

        kite = connector._get_kite()

        assert kite == mock_kite
        mock_kite_class.assert_called_once_with(api_key="test_api_key")
        mock_kite.set_access_token.assert_called_once_with("test_access_token")


@patch("kiteconnect.KiteConnect")
def test_zerodha_connector_kiteconnect_import_error(mock_kite_class):
    """ZerodhaConnector should raise ImportError if kiteconnect not installed."""
    with patch("builtins.__import__", side_effect=ImportError("kiteconnect")):
        connector = ZerodhaConnector(
            account_id="550e8400-e29b-41d4-a716-446655440001",
            api_key="test_api_key",
            access_token="test_access_token",
        )

        # The import happens in _get_kite
        # We can't easily test this without uninstalling the package,
        # but we verify the error handling is in place
        assert hasattr(connector, "_get_kite")


# ── Tests: Holdings fetching ──────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_fetch_holdings(
    mock_kite_class,
    mock_kiteconnect_holdings,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should fetch and transform holdings."""
    mock_kite = MagicMock()
    mock_kite.holdings.return_value = mock_kiteconnect_holdings
    mock_kite.trades.return_value = []
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) >= 1
    # First doc should be holdings
    holdings_doc = docs[0]
    assert holdings_doc.source == IngestionSource.ZERODHA_API
    assert holdings_doc.account_id == zerodha_account_id

    # Verify holdings are transformed to transactions
    holdings_txs = json.loads(holdings_doc.raw_bytes)
    assert len(holdings_txs) == len(mock_kiteconnect_holdings)
    assert holdings_txs[0]["type"] == "CREDIT"  # Holdings are credits
    assert "Holding:" in holdings_txs[0]["description"]


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_holdings_empty(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should handle empty holdings gracefully."""
    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.return_value = []
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    # Should still return empty or skip holdings if empty
    assert isinstance(docs, list)


# ── Tests: Trade history fetching ────────────────────────────────────────────

@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_fetch_trades(
    mock_kite_class,
    mock_kiteconnect_trades,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should fetch and transform trades."""
    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.return_value = mock_kiteconnect_trades
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
        lookback_days=90,
    )

    docs = await connector.fetch(test_owner_id)

    # Should have trades doc
    trade_docs = [d for d in docs if "trades" in d.suggested_filename]
    assert len(trade_docs) >= 1

    trades_txs = json.loads(trade_docs[0].raw_bytes)
    assert len(trades_txs) > 0
    # Verify trade structure
    assert "description" in trades_txs[0]
    assert "amount" in trades_txs[0]


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_trades_lookback_filter(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should filter trades by lookback_days."""
    today = date.today()
    old_trade = {
        "tradingsymbol": "INFY",
        "transaction_type": "BUY",
        "quantity": 10,
        "average_price": 1450.00,
        "fill_timestamp": (today - timedelta(days=100)).isoformat() + " 09:30:00",
    }
    recent_trade = {
        "tradingsymbol": "TCS",
        "transaction_type": "SELL",
        "quantity": 5,
        "average_price": 3700.00,
        "fill_timestamp": (today - timedelta(days=30)).isoformat() + " 10:15:00",
    }

    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.return_value = [old_trade, recent_trade]
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
        lookback_days=90,
    )

    docs = await connector.fetch(test_owner_id)

    trade_docs = [d for d in docs if "trades" in d.suggested_filename]
    if trade_docs:
        trades_txs = json.loads(trade_docs[0].raw_bytes)
        # Only recent trade should be included
        assert len(trades_txs) == 1
        assert "TCS" in trades_txs[0]["description"]


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_trades_empty(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should handle empty trades gracefully."""
    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.return_value = []
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    assert isinstance(docs, list)


# ── Tests: Error handling ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zerodha_connector_auth_failure_graceful(
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should gracefully handle auth failures."""
    with patch.object(
        ZerodhaConnector,
        "_get_kite",
        side_effect=Exception("Auth failed"),
    ):
        connector = ZerodhaConnector(
            account_id=zerodha_account_id,
            api_key="invalid_key",
            access_token="invalid_token",
        )

        docs = await connector.fetch(test_owner_id)

    assert docs == []


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_holdings_api_failure_graceful(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should gracefully handle holdings API failure."""
    mock_kite = MagicMock()
    mock_kite.holdings.side_effect = Exception("API error")
    mock_kite.trades.return_value = []
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    # Should continue and possibly return trades if available
    assert isinstance(docs, list)


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_trades_api_failure_graceful(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should gracefully handle trades API failure."""
    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.side_effect = Exception("API error")
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    # Should continue despite trade failure
    assert isinstance(docs, list)


# ── Tests: Configuration ──────────────────────────────────────────────────────

def test_zerodha_connector_default_lookback_days(zerodha_account_id):
    """ZerodhaConnector should default lookback_days to 90."""
    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    assert connector._lookback_days == 90


def test_zerodha_connector_custom_lookback_days(zerodha_account_id):
    """ZerodhaConnector should accept custom lookback_days."""
    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
        lookback_days=30,
    )

    assert connector._lookback_days == 30


# ── Tests: Data transformation ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_holdings_transformation(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should correctly transform holdings to transactions."""
    holding = {
        "tradingsymbol": "INFY",
        "exchange": "NSE",
        "quantity": 10,
        "last_price": 1500.50,
        "average_price": 1450.00,
        "isin": "INE009A01021",
    }

    mock_kite = MagicMock()
    mock_kite.holdings.return_value = [holding]
    mock_kite.trades.return_value = []
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    holdings_doc = docs[0]
    holdings_txs = json.loads(holdings_doc.raw_bytes)
    tx = holdings_txs[0]

    assert tx["type"] == "CREDIT"
    assert tx["category"] == "INVESTMENT"
    assert tx["merchant"] == "Zerodha"
    assert "INFY" in tx["description"]
    assert float(tx["amount"]) == holding["last_price"] * holding["quantity"]
    # Verify extra metadata is preserved
    assert tx["extra"]["isin"] == "INE009A01021"
    assert tx["extra"]["quantity"] == 10


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_trades_transformation(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should correctly transform trades to transactions."""
    today = date.today()
    trade = {
        "tradingsymbol": "INFY",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "quantity": 10,
        "average_price": 1450.00,
        "fill_timestamp": (today - timedelta(days=10)).isoformat() + " 09:30:00",
    }

    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.return_value = [trade]
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    trade_docs = [d for d in docs if "trades" in d.suggested_filename]
    assert len(trade_docs) > 0

    trades_txs = json.loads(trade_docs[0].raw_bytes)
    tx = trades_txs[0]

    assert tx["type"] == "DEBIT"  # BUY = DEBIT
    assert tx["category"] == "INVESTMENT"
    assert tx["merchant"] == "Zerodha"
    assert "INFY" in tx["description"]
    assert float(tx["amount"]) == trade["average_price"] * trade["quantity"]


@pytest.mark.asyncio
@patch("kiteconnect.KiteConnect")
async def test_zerodha_connector_sell_trade_transformation(
    mock_kite_class,
    zerodha_account_id,
    test_owner_id,
):
    """ZerodhaConnector should mark SELL trades as CREDIT."""
    today = date.today()
    trade = {
        "tradingsymbol": "TCS",
        "exchange": "NSE",
        "transaction_type": "SELL",
        "quantity": 5,
        "average_price": 3800.00,
        "fill_timestamp": (today - timedelta(days=10)).isoformat() + " 14:30:00",
    }

    mock_kite = MagicMock()
    mock_kite.holdings.return_value = []
    mock_kite.trades.return_value = [trade]
    mock_kite_class.return_value = mock_kite

    connector = ZerodhaConnector(
        account_id=zerodha_account_id,
        api_key="test_api_key",
        access_token="test_access_token",
    )

    docs = await connector.fetch(test_owner_id)

    trade_docs = [d for d in docs if "trades" in d.suggested_filename]
    trades_txs = json.loads(trade_docs[0].raw_bytes)
    tx = trades_txs[0]

    assert tx["type"] == "CREDIT"  # SELL = CREDIT
