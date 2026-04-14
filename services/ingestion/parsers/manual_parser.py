"""
Manual Parser — accepts structured JSON payloads for static/manual data.

Used for:
  - Insurance policy data
  - Real estate / gold holdings
  - Tax data (ITR summaries)
  - Financial goals
  - Any transaction not available via PDF or API

Input format (JSON bytes or dict list):
[
  {
    "date": "2024-03-15",           # or "15/03/2024"
    "description": "LIC Premium",
    "amount": "25000.00",           # Indian format string or plain number
    "type": "DEBIT",                # CREDIT or DEBIT
    "category": "INSURANCE",       # optional
    "merchant": "LIC of India"      # optional
  },
  ...
]
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import structlog

from services.ingestion.normalizers.category_mapper import map_category
from services.ingestion.normalizers.date_normalizer import parse_date
from services.ingestion.parsers.base import BaseParser, ParseError
from services.validation.models import RawTransaction

log = structlog.get_logger(__name__)


class ManualParser(BaseParser):
    """
    Parses a JSON byte payload into RawTransaction objects.
    Accepts both a list of transaction dicts and a {"transactions": [...]} wrapper.
    """

    @property
    def source_name(self) -> str:
        return "Manual JSON Input"

    def parse(
        self,
        raw_bytes: bytes,
        owner_id: uuid.UUID,
        account_id: uuid.UUID,
        password: str | None = None,
    ) -> list[RawTransaction]:
        try:
            payload = json.loads(raw_bytes)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid JSON payload: {exc}") from exc

        # Unwrap {"transactions": [...]} envelope if present
        if isinstance(payload, dict):
            payload = payload.get("transactions", [])

        if not isinstance(payload, list):
            raise ParseError("Expected a JSON array or {'transactions': [...]} object")

        transactions: list[RawTransaction] = []
        for i, item in enumerate(payload):
            if not isinstance(item, dict):
                log.warning("manual_parser.skipped_non_dict_item", index=i)
                continue

            date_text = str(item.get("date", "")).strip()
            description = str(item.get("description", "")).strip()
            amount_text = str(item.get("amount", "")).strip()
            tx_type = str(item.get("type", "DEBIT")).strip().upper()
            category = item.get("category") or map_category(description)
            merchant = item.get("merchant")

            if not description or not amount_text:
                log.warning("manual_parser.skipped_missing_fields", index=i, item=item)
                continue

            tx_date: date | None = parse_date(date_text) if date_text else None

            transactions.append(
                RawTransaction(
                    owner_id=owner_id,
                    account_id=account_id,
                    transaction_date=tx_date,
                    raw_date_text=date_text,
                    raw_amount_text=amount_text,
                    transaction_type=tx_type,
                    raw_description=description,
                    category=category,
                    merchant=merchant,
                )
            )

        log.info("manual_parser.parsed", count=len(transactions))
        return transactions
