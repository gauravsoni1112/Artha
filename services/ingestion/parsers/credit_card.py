"""
Credit Card Statement Parser — pdfplumber-based.

Supports HDFC Credit Card and Axis Bank Credit Card statement formats.
"""

from __future__ import annotations

import io
import re
import uuid
from typing import Iterator

import pdfplumber
import structlog

from services.ingestion.normalizers.category_mapper import map_category
from services.ingestion.normalizers.date_normalizer import parse_date
from services.ingestion.parsers.base import BaseParser, ParseError
from services.validation.models import RawTransaction

log = structlog.get_logger(__name__)


class _CCStrategy:
    """Generic credit card row extractor."""

    def matches(self, text: str) -> bool:
        return True  # Fallback strategy

    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        # Generic: look for tables with Date, Description, Amount columns
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(c or "").strip().lower() for c in table[0]]
                joined = " ".join(header)
                if "date" not in joined:
                    continue
                for row in table[1:]:
                    if not row or not row[0]:
                        continue
                    date_text = str(row[0] or "").strip()
                    description = str(row[1] or "").strip() if len(row) > 1 else ""
                    amount_text = str(row[-1] or "").strip()  # Last column usually amount
                    if not description or not amount_text:
                        continue
                    # Determine DEBIT/CREDIT from suffix or sign
                    lower_amt = amount_text.lower()
                    if lower_amt.endswith("cr"):
                        tx_type = "CREDIT"
                    else:
                        tx_type = "DEBIT"
                    yield {
                        "date_text": date_text,
                        "description": description,
                        "amount_text": amount_text,
                        "tx_type": tx_type,
                    }


class _HDFCCCStrategy(_CCStrategy):
    """HDFC Credit Card statement (Dr/Cr column format)."""

    def matches(self, text: str) -> bool:
        return bool(re.search(r"HDFC\s*BANK\s*CREDIT|CREDIT\s*CARD\s*STATEMENT", text, re.I))

    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = " ".join(str(c or "") for c in table[0]).lower()
                if "transaction" not in header and "date" not in header:
                    continue
                for row in table[1:]:
                    if not row or len(row) < 3:
                        continue
                    date_text = str(row[0] or "").strip()
                    description = str(row[1] or "").strip()
                    amount_text = str(row[2] or "").strip()
                    if not date_text or not description:
                        continue
                    lower = amount_text.lower()
                    tx_type = "CREDIT" if lower.endswith("cr") else "DEBIT"
                    yield {
                        "date_text": date_text,
                        "description": description,
                        "amount_text": amount_text,
                        "tx_type": tx_type,
                    }


_CC_STRATEGIES: list[_CCStrategy] = [
    _HDFCCCStrategy(),
    _CCStrategy(),  # generic fallback
]


class CreditCardParser(BaseParser):
    """Parse credit card statement PDFs."""

    @property
    def source_name(self) -> str:
        return "Credit Card Statement (PDF)"

    def parse(
        self,
        raw_bytes: bytes,
        owner_id: uuid.UUID,
        account_id: uuid.UUID,
    ) -> list[RawTransaction]:
        try:
            pdf = pdfplumber.open(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise ParseError(f"Cannot open PDF: {exc}") from exc

        first_page_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
        strategy = next((s for s in _CC_STRATEGIES if s.matches(first_page_text)), _CC_STRATEGIES[-1])

        transactions: list[RawTransaction] = []
        for row in strategy.extract_rows(pdf):
            tx_date = parse_date(row["date_text"])
            transactions.append(
                RawTransaction(
                    owner_id=owner_id,
                    account_id=account_id,
                    transaction_date=tx_date,
                    raw_date_text=row["date_text"],
                    raw_amount_text=row["amount_text"],
                    transaction_type=row["tx_type"],
                    raw_description=row["description"],
                    category=map_category(row["description"]),
                )
            )

        log.info("credit_card.parsed", count=len(transactions))
        return transactions
