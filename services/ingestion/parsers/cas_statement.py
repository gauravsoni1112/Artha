"""
Mutual Fund CAS (Consolidated Account Statement) Parser.

CAMS/KFintech CAS PDFs are complex multi-column documents.
Uses camelot-py for precise table extraction.

CAS structure per folio:
  - Folio number, Fund name, ISIN
  - Transaction table: Date | Transaction | Amount | Units | NAV | Balance Units

Output: RawTransaction records for each MF transaction (Purchase, Redemption,
Dividend, SIP, STP, etc.), plus Holding records (not emitted here — holdings are
handled separately by IngestionService).
"""

from __future__ import annotations

import io
import re
import tempfile
import uuid
import os
from typing import Iterator

import structlog

from services.ingestion.normalizers.category_mapper import map_category
from services.ingestion.normalizers.date_normalizer import parse_date
from services.ingestion.parsers.base import BaseParser, ParseError
from services.validation.models import RawTransaction

log = structlog.get_logger(__name__)

# Transaction types that map to CREDIT (units purchased)
_PURCHASE_TYPES = re.compile(
    r"\b(purchase|sip|new folio|switch in|stp in|dividend reinvest|systematic investment)\b", re.I
)
# Transaction types that map to DEBIT (units redeemed)
_REDEMPTION_TYPES = re.compile(r"\b(redemption|switch out|stp out)\b", re.I)

# Matches a CAS transaction text line:
#   DD-Mon-YYYY  <description>  amount  units  nav  unit_balance
# Stamp Duty lines (only one trailing number) intentionally do NOT match.
_CAS_TX_LINE_RE = re.compile(
    r"^(\d{2}-[A-Za-z]{3}-\d{4})"      # date
    r"\s+(.+?)"                          # description (non-greedy)
    r"\s+(-?[\d,]+\.\d+)"               # amount
    r"\s+(-?[\d,]+\.\d+)"               # units
    r"\s+(-?[\d,]+\.\d+)"               # nav/price
    r"\s+(-?[\d,]+\.\d+)\s*$",          # unit balance
    re.MULTILINE,
)


def _classify_mf_tx(description: str) -> str:
    if _PURCHASE_TYPES.search(description):
        return "CREDIT"
    if _REDEMPTION_TYPES.search(description):
        return "DEBIT"
    return "CREDIT"  # Default: treat as purchase


class CASStatementParser(BaseParser):
    """
    Parse CAMS/KFintech Consolidated Account Statement PDFs.

    Uses camelot for table extraction; falls back to pdfplumber text parsing
    if camelot cannot find tables (e.g. scanned PDFs).
    """

    @property
    def source_name(self) -> str:
        return "Mutual Fund CAS (PDF)"

    def parse(
        self,
        raw_bytes: bytes,
        owner_id: uuid.UUID,
        account_id: uuid.UUID,
        password: str | None = None,
    ) -> list[RawTransaction]:
        # camelot requires a file path, not bytes — write to a temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            return self._parse_with_camelot(tmp_path, owner_id, account_id)
        except Exception as exc:
            log.warning("cas.camelot_failed_falling_back", error=str(exc))
            return self._parse_with_pdfplumber(raw_bytes, owner_id, account_id, password=password)
        finally:
            os.unlink(tmp_path)

    def _parse_with_camelot(
        self, path: str, owner_id: uuid.UUID, account_id: uuid.UUID
    ) -> list[RawTransaction]:
        import camelot

        tables = camelot.read_pdf(path, pages="all", flavor="lattice")
        if not tables or tables.n == 0:
            tables = camelot.read_pdf(path, pages="all", flavor="stream")

        transactions: list[RawTransaction] = []
        for table in tables:
            df = table.df
            if df.empty or df.shape[1] < 4:
                continue
            for _, row in df.iterrows():
                tx = self._row_to_transaction(row.tolist(), owner_id, account_id)
                if tx:
                    transactions.append(tx)

        log.info("cas.parsed_camelot", count=len(transactions))
        return transactions

    def _parse_with_pdfplumber(
        self, raw_bytes: bytes, owner_id: uuid.UUID, account_id: uuid.UUID,
        password: str | None = None,
    ) -> list[RawTransaction]:
        import pdfplumber

        open_kwargs = {"password": password} if password else {}
        full_text_lines: list[str] = []
        with pdfplumber.open(io.BytesIO(raw_bytes), **open_kwargs) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text_lines.extend(text.splitlines())

        transactions: list[RawTransaction] = []
        for line in full_text_lines:
            tx = self._text_line_to_transaction(line.strip(), owner_id, account_id)
            if tx:
                transactions.append(tx)

        log.info("cas.parsed_pdfplumber_fallback", count=len(transactions))
        return transactions

    def _text_line_to_transaction(
        self, line: str, owner_id: uuid.UUID, account_id: uuid.UUID
    ) -> RawTransaction | None:
        """Parse a single CAS text line of the form:
        DD-Mon-YYYY  <description>  amount  units  nav  unit_balance
        Stamp Duty lines (one trailing number) are skipped.
        """
        m = _CAS_TX_LINE_RE.match(line)
        if not m:
            return None

        date_text, description, amount_text = m.group(1), m.group(2).strip(), m.group(3)
        tx_date = parse_date(date_text)
        tx_type = _classify_mf_tx(description)

        return RawTransaction(
            owner_id=owner_id,
            account_id=account_id,
            transaction_date=tx_date,
            raw_date_text=date_text,
            raw_amount_text=amount_text,
            transaction_type=tx_type,
            raw_description=description,
            category=map_category(description),
        )

    def _row_to_transaction(
        self, row: list, owner_id: uuid.UUID, account_id: uuid.UUID
    ) -> RawTransaction | None:
        if not row or len(row) < 4:
            return None

        date_text = str(row[0] or "").strip()
        description = str(row[1] or "").strip()
        amount_text = str(row[2] or "").strip()

        if not date_text or not description or not amount_text:
            return None

        tx_date = parse_date(date_text)
        tx_type = _classify_mf_tx(description)

        # Strip any unit/NAV columns — we only want the transaction amount
        amount_text = re.sub(r"[^\d,.\-₹]", "", amount_text).strip()
        if not amount_text:
            return None

        return RawTransaction(
            owner_id=owner_id,
            account_id=account_id,
            transaction_date=tx_date,
            raw_date_text=date_text,
            raw_amount_text=amount_text,
            transaction_type=tx_type,
            raw_description=description,
            category=map_category(description),
        )
