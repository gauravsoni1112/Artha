"""
Shared fixtures for ingestion unit tests.

Provides mock credentials, API responses, and test data for connectors.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from libs.schemas.enums import DocumentType, IngestionSource


# ── Fixtures: Test data ───────────────────────────────────────────────────────

@pytest.fixture
def test_owner_id() -> uuid.UUID:
    """A consistent test owner UUID."""
    return uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def test_account_id() -> uuid.UUID:
    """A consistent test account UUID."""
    return uuid.UUID("550e8400-e29b-41d4-a716-446655440001")


@pytest.fixture
def sample_manual_payload() -> bytes:
    """Sample JSON payload for manual connector testing."""
    return json.dumps({
        "transactions": [
            {
                "date": "15/06/2024",
                "description": "SALARY CREDIT",
                "amount": "1,00,000.00",
                "type": "CREDIT",
                "category": "SALARY",
            },
            {
                "date": "01/06/2024",
                "description": "Grocery Shopping",
                "amount": "2,500.00",
                "type": "DEBIT",
            },
        ]
    }).encode()


# ── Fixtures: Gmail mocks ─────────────────────────────────────────────────────

@pytest.fixture
def mock_gmail_creds():
    """Mock Google OAuth2 credentials."""
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "mock_refresh_token"
    creds.to_json.return_value = '{"token": "mock_token"}'
    return creds


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail API service."""
    service = MagicMock()

    # Mock search results
    messages = MagicMock()
    messages_list = MagicMock()
    messages_list.list.return_value.execute.return_value = {
        "messages": [
            {"id": "msg_123"},
            {"id": "msg_456"},
        ]
    }
    messages.list.return_value = messages_list

    # Mock message get (with attachments)
    message_get = MagicMock()
    message_get.execute.return_value = {
        "id": "msg_123",
        "payload": {
            "parts": [
                {
                    "filename": "statement_jun_2024.pdf",
                    "mimeType": "application/pdf",
                    "body": {
                        "attachmentId": "att_789"
                    }
                }
            ]
        }
    }
    messages.get.return_value = message_get

    # Mock attachment get
    attachments = MagicMock()
    attachment_get = MagicMock()
    attachment_get.execute.return_value = {
        "data": "JVBERi0xLjQKJU1vY2sgQmFuayBTdGF0ZW1lbnQgUERGCiUlRU9G"  # base64 of "%PDF-1.4\n%Mock..."
    }
    attachments.get.return_value = attachment_get
    messages.attachments.return_value = attachments

    service.users.return_value.messages.return_value = messages
    return service


# ── Fixtures: Zerodha mocks ──────────────────────────────────────────────────

@pytest.fixture
def mock_kiteconnect_holdings():
    """Mock Zerodha holdings response."""
    return [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "quantity": 10,
            "last_price": 1500.50,
            "average_price": 1450.00,
            "isin": "INE009A01021",
        },
        {
            "tradingsymbol": "TCS",
            "exchange": "NSE",
            "quantity": 5,
            "last_price": 3800.00,
            "average_price": 3700.00,
            "isin": "INE467B01029",
        },
    ]


@pytest.fixture
def mock_kiteconnect_trades():
    """Mock Zerodha trades response."""
    from datetime import date, timedelta
    today = date.today()
    return [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "average_price": 1450.00,
            "fill_timestamp": (today - timedelta(days=10)).isoformat() + " 09:30:00",
        },
        {
            "tradingsymbol": "TCS",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 5,
            "average_price": 3700.00,
            "fill_timestamp": (today - timedelta(days=20)).isoformat() + " 10:15:00",
        },
    ]


@pytest.fixture
def mock_kiteconnect():
    """Mock KiteConnect instance."""
    kite = MagicMock()
    kite.holdings.return_value = []  # Default empty, override as needed
    kite.trades.return_value = []    # Default empty, override as needed
    return kite


# ── Fixtures: Connector fixtures ──────────────────────────────────────────────

@pytest.fixture
def gmail_account_id_map(test_account_id) -> dict:
    """Account ID mapping for Gmail document types."""
    return {
        DocumentType.BANK_STATEMENT: test_account_id,
        DocumentType.CC_STATEMENT: test_account_id,
        DocumentType.MF_CAS: test_account_id,
    }


@pytest.fixture
def zerodha_account_id(test_account_id) -> uuid.UUID:
    """Test Zerodha account ID."""
    return test_account_id
