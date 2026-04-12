"""Unit tests for ManualParser."""

import json
import uuid
import pytest

from services.ingestion.parsers.manual_parser import ManualParser
from services.ingestion.parsers.base import ParseError


@pytest.fixture
def parser():
    return ManualParser()


@pytest.fixture
def owner_id():
    return uuid.uuid4()


@pytest.fixture
def account_id():
    return uuid.uuid4()


class TestManualParser:
    def test_parses_list_payload(self, parser, owner_id, account_id):
        payload = json.dumps([
            {
                "date": "15/03/2024",
                "description": "LIC Premium",
                "amount": "25000.00",
                "type": "DEBIT",
                "category": "INSURANCE",
            }
        ]).encode()
        txs = parser.parse(payload, owner_id, account_id)
        assert len(txs) == 1
        assert txs[0].raw_description == "LIC Premium"
        assert txs[0].raw_amount_text == "25000.00"
        assert txs[0].transaction_type == "DEBIT"
        assert txs[0].category == "INSURANCE"

    def test_parses_envelope_format(self, parser, owner_id, account_id):
        payload = json.dumps({
            "transactions": [
                {"date": "01/04/2024", "description": "Salary", "amount": "1,00,000", "type": "CREDIT"}
            ]
        }).encode()
        txs = parser.parse(payload, owner_id, account_id)
        assert len(txs) == 1
        assert txs[0].transaction_type == "CREDIT"

    def test_invalid_json_raises(self, parser, owner_id, account_id):
        with pytest.raises(ParseError):
            parser.parse(b"not json", owner_id, account_id)

    def test_skips_items_with_missing_fields(self, parser, owner_id, account_id):
        payload = json.dumps([
            {"description": ""},  # missing amount → should be skipped
            {"date": "01/01/2024", "description": "Valid Tx", "amount": "500", "type": "DEBIT"},
        ]).encode()
        txs = parser.parse(payload, owner_id, account_id)
        assert len(txs) == 1
        assert txs[0].raw_description == "Valid Tx"

    def test_owner_and_account_ids_set(self, parser, owner_id, account_id):
        payload = json.dumps([
            {"date": "01/01/2024", "description": "Test", "amount": "100", "type": "DEBIT"}
        ]).encode()
        txs = parser.parse(payload, owner_id, account_id)
        assert txs[0].owner_id == owner_id
        assert txs[0].account_id == account_id

    def test_auto_categorisation(self, parser, owner_id, account_id):
        payload = json.dumps([
            {"date": "01/01/2024", "description": "Zomato food order", "amount": "350", "type": "DEBIT"}
        ]).encode()
        txs = parser.parse(payload, owner_id, account_id)
        assert txs[0].category == "DINING"
