"""
Bank Statement Parser — pdfplumber-based.

Supports tabular bank statements from major Indian banks:
  HDFC, SBI, ICICI, Axis, Kotak

Each bank class detects itself by inspecting the first page text.
BankStatementParser auto-selects the correct bank strategy.
"""

from __future__ import annotations

import io
import re
import uuid
from abc import ABC, abstractmethod
from typing import Iterator

import pdfplumber
import structlog

from services.ingestion.normalizers.category_mapper import map_category
from services.ingestion.normalizers.date_normalizer import parse_date
from services.ingestion.parsers.base import BaseParser, ParseError
from services.validation.models import RawTransaction

log = structlog.get_logger(__name__)


def _parse_float(s: str) -> float:
    """Parse a comma-formatted number like '1,234.56' to float."""
    return float(s.replace(',', ''))


# ─────────────────────────────────────────────────────────────────────────────
# Bank strategy ABC
# ─────────────────────────────────────────────────────────────────────────────

class _BankStrategy(ABC):
    """Bank-specific row extraction logic."""

    @abstractmethod
    def matches(self, first_page_text: str) -> bool:
        """Return True if this strategy should handle the document."""

    @abstractmethod
    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        """
        Yield row dicts with keys:
          date_text, description, debit_text, credit_text, balance_text (optional)
        """


class _HDFCStrategy(_BankStrategy):
    """HDFC Bank savings/current account statement."""

    # HDFC table headers (case-insensitive)
    _DATE_COL = re.compile(r"date", re.I)
    _NARR_COL = re.compile(r"narration|description|particulars", re.I)
    _DEBIT_COL = re.compile(r"withdrawal|debit", re.I)
    _CREDIT_COL = re.compile(r"deposit|credit", re.I)

    def matches(self, text: str) -> bool:
        return bool(re.search(r"HDFC\s*BANK", text, re.I))

    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(c or "").strip() for c in table[0]]
                try:
                    date_idx = next(i for i, h in enumerate(header) if self._DATE_COL.search(h))
                    narr_idx = next(i for i, h in enumerate(header) if self._NARR_COL.search(h))
                    deb_idx = next(i for i, h in enumerate(header) if self._DEBIT_COL.search(h))
                    cred_idx = next(i for i, h in enumerate(header) if self._CREDIT_COL.search(h))
                except StopIteration:
                    continue  # header row not found in this table

                for row in table[1:]:
                    if not row or not row[date_idx]:
                        continue
                    yield {
                        "date_text": str(row[date_idx] or "").strip(),
                        "description": str(row[narr_idx] or "").strip(),
                        "debit_text": str(row[deb_idx] or "").strip(),
                        "credit_text": str(row[cred_idx] or "").strip(),
                    }


class _SBIStrategy(_BankStrategy):
    """SBI savings account statement."""

    def matches(self, text: str) -> bool:
        return bool(re.search(r"STATE\s*BANK\s*OF\s*INDIA|SBI", text, re.I))

    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(c or "").strip().lower() for c in table[0]]
                if "txn date" not in " ".join(header) and "date" not in header:
                    continue
                for row in table[1:]:
                    if not row or len(row) < 4:
                        continue
                    yield {
                        "date_text": str(row[0] or "").strip(),
                        "description": str(row[1] or "").strip(),
                        "debit_text": str(row[2] or "").strip(),
                        "credit_text": str(row[3] or "").strip(),
                    }


class _KotakStrategy(_BankStrategy):
    """Kotak Bank savings/current account statement.

    Kotak PDFs render a table whose first row is a section title
    ("Savings Account Transactions") and second row is the real header.
    Matched by the KKBK IFSC prefix present on every Kotak statement.
    """

    _DATE_COL = re.compile(r"^date$", re.I)
    _NARR_COL = re.compile(r"description", re.I)
    _DEBIT_COL = re.compile(r"withdrawal", re.I)
    _CREDIT_COL = re.compile(r"deposit", re.I)

    def matches(self, text: str) -> bool:
        return bool(re.search(r"KKBK\d+", text, re.I))

    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Kotak tables start with a title row; find the real header row.
                header_idx = None
                for r_idx in range(min(3, len(table))):
                    cells = [str(c or "").strip() for c in table[r_idx]]
                    if any(self._DATE_COL.search(c) for c in cells):
                        header_idx = r_idx
                        break
                if header_idx is None:
                    continue

                header = [str(c or "").strip() for c in table[header_idx]]
                try:
                    date_idx = next(i for i, h in enumerate(header) if self._DATE_COL.search(h))
                    narr_idx = next(i for i, h in enumerate(header) if self._NARR_COL.search(h))
                    deb_idx = next(i for i, h in enumerate(header) if self._DEBIT_COL.search(h))
                    cred_idx = next(i for i, h in enumerate(header) if self._CREDIT_COL.search(h))
                except StopIteration:
                    continue

                for row in table[header_idx + 1:]:
                    if not row:
                        continue
                    date_val = str(row[date_idx] or "").strip()
                    if not date_val or date_val == "-":
                        continue
                    # Multiline cells (pdfplumber joins with \n) — normalise to space
                    description = str(row[narr_idx] or "").strip().replace("\n", " ")
                    yield {
                        "date_text": date_val,
                        "description": description,
                        "debit_text": str(row[deb_idx] or "").strip(),
                        "credit_text": str(row[cred_idx] or "").strip(),
                    }


class _ICICIStrategy(_BankStrategy):
    """
    ICICI Bank savings account statement — text layout-based extraction.

    ICICI PDFs render transactions as fixed-width text, not proper PDF tables.
    Each transaction line looks like:
        DD-MM-YYYY  [REFERENCE]  AMOUNT  RUNNING_BALANCE
    with the human-readable UPI/NEFT description on the preceding line(s).
    Credit vs debit is determined by whether the running balance increased or
    decreased relative to the previous transaction.
    """

    # Line starting with DD-MM-YYYY
    _DATE_RE = re.compile(r"^\s*(\d{2}-\d{2}-\d{4})\s+(.*)")
    # Currency amounts: digits+commas followed by exactly 2 decimal places
    _MONEY_RE = re.compile(r"[\d,]+\.\d{2}")
    # Lines that are page chrome / footer — skip entirely
    _SKIP_RE = re.compile(
        r"^(DATE\s+MODE|Total:|Statement of|ACCOUNT|Page \d|TOTAL|"
        r"Sincerely|Team ICICI|This is a system|You can now|Card blocking|"
        r"iMobile|Personal Banking|Internet Banking|InstaBIZ|Corporate|"
        r"Account blocking|SMS:|W\.e\.f\.|Legends|VAT/MAT|EBA /|VPS/|RTGS|"
        r"Customers are|Registration|Registered Office|Corporate Office|"
        r"Effective Sep|l ICICI|l T |l Update|l Bank|l A |l The|"
        r"excluding Bank|the Form)",
        re.I,
    )

    def matches(self, text: str) -> bool:
        return bool(re.search(r"ICICI\s*BANK", text, re.I))

    def extract_rows(self, pdf: pdfplumber.PDF) -> Iterator[dict]:
        prev_balance: float | None = None
        pending_desc: list[str] = []

        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text:
                continue

            for raw_line in text.split("\n"):
                line = raw_line.strip()
                if not line or self._SKIP_RE.match(line):
                    continue

                date_m = self._DATE_RE.match(line)
                if not date_m:
                    # Non-date line: accumulate as description context for next tx
                    pending_desc.append(line)
                    continue

                date_text = date_m.group(1)
                rest = date_m.group(2).strip()

                amounts = self._MONEY_RE.findall(rest)

                if len(amounts) < 2:
                    # Opening balance line (B/F) or unrecognised — track balance only
                    if amounts:
                        prev_balance = _parse_float(amounts[-1])
                    pending_desc = []
                    continue

                # Last two decimal-formatted numbers: transaction amount + running balance
                amount_str = amounts[-2]
                balance_str = amounts[-1]
                amount_val = _parse_float(amount_str)
                new_balance = _parse_float(balance_str)

                # Text before the first amount on this line is the inline reference
                desc_on_line = self._MONEY_RE.split(rest)[0].strip()

                # Combine: pending context lines + inline reference
                # Filter out single-token lines (no spaces) — these are trailing
                # reference fragments from the previous transaction, not descriptions.
                all_parts = [p for p in pending_desc if p and " " in p]
                if desc_on_line:
                    all_parts.append(desc_on_line)
                description = " ".join(all_parts).strip() or f"TX {date_text}"

                # Determine credit vs debit from balance movement
                if prev_balance is not None:
                    diff = new_balance - prev_balance
                    if abs(abs(diff) - amount_val) < 0.02:
                        tx_type = "CREDIT" if diff > 0 else "DEBIT"
                    else:
                        log.warning(
                            "icici.balance_mismatch",
                            date=date_text,
                            amount=amount_val,
                            prev=prev_balance,
                            new=new_balance,
                        )
                        prev_balance = new_balance
                        pending_desc = []
                        continue
                else:
                    tx_type = "DEBIT"  # fallback when no prior balance

                prev_balance = new_balance
                pending_desc = []

                yield {
                    "date_text": date_text,
                    "description": description,
                    "debit_text": amount_str if tx_type == "DEBIT" else "",
                    "credit_text": amount_str if tx_type == "CREDIT" else "",
                }


# ─────────────────────────────────────────────────────────────────────────────
# BankStatementParser
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGIES: list[_BankStrategy] = [
    _HDFCStrategy(),
    _SBIStrategy(),
    _KotakStrategy(),
    _ICICIStrategy(),
]


class BankStatementParser(BaseParser):
    """
    Auto-detects the bank from the PDF and extracts transactions.
    Falls back to a generic column-based extraction if no strategy matches.
    """

    @property
    def source_name(self) -> str:
        return "Bank Statement (PDF)"

    def parse(
        self,
        raw_bytes: bytes,
        owner_id: uuid.UUID,
        account_id: uuid.UUID,
        password: str | None = None,
    ) -> list[RawTransaction]:
        try:
            pdf = pdfplumber.open(io.BytesIO(raw_bytes), password=password)
        except Exception as exc:
            raise ParseError(f"Cannot open PDF: {exc}") from exc

        first_page_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""

        strategy = next(
            (s for s in _STRATEGIES if s.matches(first_page_text)), None
        )
        if strategy is None:
            log.warning("bank_statement.no_strategy_matched", hint=first_page_text[:120])
            # Generic fallback — try the first strategy's logic
            strategy = _HDFCStrategy()

        transactions: list[RawTransaction] = []

        for row in strategy.extract_rows(pdf):
            date_text = row.get("date_text", "")
            description = row.get("description", "")
            debit_text = row.get("debit_text", "").strip()
            credit_text = row.get("credit_text", "").strip()

            if not description:
                continue

            tx_date = parse_date(date_text)

            # Determine direction
            if debit_text and debit_text not in ("", "0", "0.00", "-"):
                raw_amount_text = debit_text
                tx_type = "DEBIT"
            elif credit_text and credit_text not in ("", "0", "0.00", "-"):
                raw_amount_text = credit_text
                tx_type = "CREDIT"
            else:
                log.debug("bank_statement.row_skipped_no_amount", description=description)
                continue

            transactions.append(
                RawTransaction(
                    owner_id=owner_id,
                    account_id=account_id,
                    transaction_date=tx_date,
                    raw_date_text=date_text,
                    raw_amount_text=raw_amount_text,
                    transaction_type=tx_type,
                    raw_description=description,
                    category=map_category(description),
                )
            )

        log.info(
            "bank_statement.parsed",
            source=strategy.__class__.__name__,
            count=len(transactions),
        )
        return transactions
