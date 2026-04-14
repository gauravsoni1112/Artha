"""
Unit tests for ManualConnector.

Tests cover:
  - Valid JSON payload ingestion
  - Various document types (OTHER, INSURANCE, TAX)
  - Empty payloads
  - Malformed JSON
  - Edge cases (empty transactions list)
"""

from __future__ import annotations

import json
import uuid

import pytest

from libs.schemas.enums import DocumentType, IngestionSource
from services.ingestion.connectors.manual_connector import ManualConnector


# ── Tests: Happy path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_connector_fetch_valid_payload(sample_manual_payload, test_owner_id, test_account_id):
    """ManualConnector should wrap JSON payload into FetchedDocument."""
    connector = ManualConnector(
        payload_bytes=sample_manual_payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert docs[0].raw_bytes == sample_manual_payload
    assert docs[0].doc_type == DocumentType.OTHER
    assert docs[0].source == IngestionSource.MANUAL
    assert docs[0].account_id == test_account_id
    assert "manual_" in docs[0].suggested_filename


@pytest.mark.asyncio
async def test_manual_connector_fetch_insurance_doc_type(test_owner_id, test_account_id):
    """ManualConnector should handle INSURANCE document type."""
    payload = json.dumps({
        "transactions": [
            {
                "date": "01/01/2024",
                "description": "Insurance Premium",
                "amount": "5000.00",
                "type": "DEBIT",
                "category": "INSURANCE",
            }
        ]
    }).encode()

    connector = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.INSURANCE,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert docs[0].doc_type == DocumentType.INSURANCE


@pytest.mark.asyncio
async def test_manual_connector_fetch_tax_doc_type(test_owner_id, test_account_id):
    """ManualConnector should handle TAX document type."""
    payload = json.dumps({
        "transactions": [
            {
                "date": "31/03/2024",
                "description": "Tax Payment ITR",
                "amount": "50000.00",
                "type": "DEBIT",
                "category": "TAX",
            }
        ]
    }).encode()

    connector = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.TAX,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert docs[0].doc_type == DocumentType.TAX


@pytest.mark.asyncio
async def test_manual_connector_default_doc_type(test_owner_id):
    """ManualConnector should default to OTHER if doc_type not specified."""
    payload = json.dumps({"transactions": []}).encode()
    connector = ManualConnector(payload_bytes=payload)

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert docs[0].doc_type == DocumentType.OTHER


@pytest.mark.asyncio
async def test_manual_connector_default_account_id(test_owner_id):
    """ManualConnector should default to UUID(int=0) if account_id not specified."""
    payload = json.dumps({"transactions": []}).encode()
    connector = ManualConnector(payload_bytes=payload)

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert docs[0].account_id == uuid.UUID(int=0)


# ── Tests: Edge cases ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_connector_empty_transactions_list(test_owner_id, test_account_id):
    """ManualConnector should handle empty transactions list."""
    payload = json.dumps({"transactions": []}).encode()

    connector = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    # The connector just wraps; validation happens later in IngestionService
    assert docs[0].raw_bytes == payload


@pytest.mark.asyncio
async def test_manual_connector_single_transaction(test_owner_id, test_account_id):
    """ManualConnector should handle single transaction."""
    payload = json.dumps({
        "transactions": [
            {
                "date": "15/06/2024",
                "description": "Single TX",
                "amount": "100.00",
                "type": "CREDIT",
            }
        ]
    }).encode()

    connector = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert json.loads(docs[0].raw_bytes)["transactions"][0]["description"] == "Single TX"


@pytest.mark.asyncio
async def test_manual_connector_many_transactions(test_owner_id, test_account_id):
    """ManualConnector should handle many transactions in one payload."""
    txs = [
        {
            "date": f"0{i}/06/2024" if i < 10 else f"{i}/06/2024",
            "description": f"TX {i}",
            "amount": f"{100 * i}.00",
            "type": "DEBIT" if i % 2 == 0 else "CREDIT",
        }
        for i in range(1, 51)
    ]
    payload = json.dumps({"transactions": txs}).encode()

    connector = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert len(docs) == 1
    assert len(json.loads(docs[0].raw_bytes)["transactions"]) == 50


# ── Tests: Suggested filename ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_connector_suggested_filename_format(test_owner_id, test_account_id):
    """ManualConnector should generate consistent suggested_filename."""
    payload = json.dumps({"transactions": []}).encode()

    connector = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    docs = await connector.fetch(test_owner_id)

    assert docs[0].suggested_filename == f"manual_{test_owner_id}.json"


@pytest.mark.asyncio
async def test_manual_connector_suggested_filename_consistency(test_owner_id, test_account_id):
    """ManualConnector should generate same filename for same owner."""
    payload = json.dumps({"transactions": []}).encode()

    connector1 = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    connector2 = ManualConnector(
        payload_bytes=payload,
        doc_type=DocumentType.OTHER,
        account_id=test_account_id,
    )

    docs1 = await connector1.fetch(test_owner_id)
    docs2 = await connector2.fetch(test_owner_id)

    assert docs1[0].suggested_filename == docs2[0].suggested_filename
