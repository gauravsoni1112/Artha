"""
ValidationPipeline — 4-stage data quality pipeline.

Stages (in order):
  1. SCHEMA    — Pydantic v2 field validation (required fields, types, nulls)
  2. RANGE     — Business rule / sanity checks (no future dates, salary > 0 …)
  3. ANOMALY   — Statistical spike detection (>2.5× rolling 90-day average)
  4. LOCALE    — Indian number format → paise integer conversion

Any failure at a stage immediately produces a PipelineResult.fail(stage, errors).
Records that pass all four stages get PipelineResult.pass_(record).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import date
from typing import Protocol

import structlog

from libs.schemas.money import parse_inr_to_paise
from services.validation.models import PipelineResult, RawTransaction

log = structlog.get_logger(__name__)

# ── Anomaly detection threshold ──────────────────────────────────────────────
_ANOMALY_THRESHOLD: float = float(os.getenv("ANOMALY_THRESHOLD", "2.5"))

# ── Maximum plausible single transaction: ₹10 crore ─────────────────────────
_MAX_AMOUNT_PAISE: int = 10_00_00_000 * 100  # 10 Cr in paise


# ─────────────────────────────────────────────────────────────────────────────
# SpendHistoryPort — protocol that the AnomalyDetector depends on.
# The real implementation queries PostgreSQL; tests inject InMemorySpendHistory.
# ─────────────────────────────────────────────────────────────────────────────

class SpendHistoryPort(Protocol):
    """Read-only view of historical spend for anomaly detection."""

    def get_rolling_average_paise(
        self,
        owner_id: str,
        category: str | None,
        window_days: int = 90,
    ) -> int | None:
        """
        Return the rolling average daily spend in paise for the given owner/category
        over the last `window_days`, or None if there is insufficient history.
        """
        ...


class InMemorySpendHistory:
    """
    Simple in-memory implementation of SpendHistoryPort.
    Used in unit tests; pre-loaded with a dict of {(owner_id, category): avg_paise}.
    """

    def __init__(self, history: dict[tuple[str, str | None], int] | None = None) -> None:
        self._history: dict[tuple[str, str | None], int] = history or {}

    def set(self, owner_id: str, category: str | None, avg_paise: int) -> None:
        self._history[(owner_id, category)] = avg_paise

    def get_rolling_average_paise(
        self,
        owner_id: str,
        category: str | None,
        window_days: int = 90,
    ) -> int | None:
        return self._history.get((owner_id, category))


# ─────────────────────────────────────────────────────────────────────────────
# Individual stage implementations
# ─────────────────────────────────────────────────────────────────────────────

class _Stage(ABC):
    @abstractmethod
    def run(self, record: RawTransaction) -> list[str]:
        """Return a list of error strings; empty list means the record passed."""


class SchemaValidator(_Stage):
    """
    Stage 1: Ensure required fields are present and have the right types.

    Required: owner_id, account_id, raw_date_text or transaction_date,
              raw_amount_text, transaction_type.
    """

    _REQUIRED_NON_EMPTY = [
        "raw_amount_text",
        "transaction_type",
    ]
    _VALID_TX_TYPES = {"CREDIT", "DEBIT"}

    def run(self, record: RawTransaction) -> list[str]:
        errors: list[str] = []

        # Date must be present in some form
        if not record.transaction_date and not record.raw_date_text:
            errors.append("transaction_date or raw_date_text is required")

        # Non-empty string fields
        for field in self._REQUIRED_NON_EMPTY:
            value = getattr(record, field, None)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"Field '{field}' is required and must not be empty")

        # Transaction type enum check
        if record.transaction_type and record.transaction_type not in self._VALID_TX_TYPES:
            errors.append(
                f"Invalid transaction_type '{record.transaction_type}'. "
                f"Must be one of {self._VALID_TX_TYPES}"
            )

        # Description — at least one must be present
        if not record.description and not record.raw_description:
            errors.append("Either 'description' or 'raw_description' must be provided")

        return errors


class RangeValidator(_Stage):
    """
    Stage 2: Business logic / sanity checks.
    """

    def run(self, record: RawTransaction) -> list[str]:
        errors: list[str] = []

        # No future-dated transactions
        if record.transaction_date and record.transaction_date > date.today():
            errors.append(
                f"Future-dated transaction: {record.transaction_date} is after today"
            )

        # Salary income must be positive (credit)
        if (
            record.category == "SALARY"
            and record.amount_paise is not None
            and record.amount_paise <= 0
        ):
            errors.append("Salary transaction must have a positive amount (CREDIT)")

        # If amount_paise is already set (e.g. from a structured API source), validate range
        if record.amount_paise is not None:
            if record.amount_paise == 0:
                errors.append("Transaction amount cannot be zero")
            if abs(record.amount_paise) > _MAX_AMOUNT_PAISE:
                errors.append(
                    f"Transaction amount ₹{abs(record.amount_paise) // 100:,} "
                    f"exceeds maximum plausible value of ₹10 crore"
                )

        # Currency must be INR (foreign currency transactions are out of scope for Phase 1)
        if record.currency and record.currency != "INR":
            errors.append(
                f"Non-INR currency '{record.currency}' is not supported in Phase 1"
            )

        return errors


class AnomalyDetector(_Stage):
    """
    Stage 3: Flag transactions that are >ANOMALY_THRESHOLD × rolling 90-day average.

    Only triggers when there is sufficient history (≥30 days of data).
    Uses SpendHistoryPort so the DB dependency is injectable.
    """

    def __init__(self, spend_history: SpendHistoryPort, threshold: float = _ANOMALY_THRESHOLD) -> None:
        self._history = spend_history
        self._threshold = threshold

    def run(self, record: RawTransaction) -> list[str]:
        # Only check if we have the parsed amount (may be pre-set for API sources)
        amount = record.amount_paise
        if amount is None:
            # Amount not yet parsed — defer to LOCALE stage; skip anomaly check
            return []

        abs_amount = abs(amount)
        owner_id = str(record.owner_id)
        avg = self._history.get_rolling_average_paise(owner_id, record.category)

        if avg is None or avg == 0:
            # No history — cannot determine anomaly; let it pass
            return []

        if abs_amount > self._threshold * avg:
            ratio = abs_amount / avg
            return [
                f"Anomaly detected: amount ₹{abs_amount // 100:,} is {ratio:.1f}× "
                f"the 90-day rolling average ₹{avg // 100:,} "
                f"(threshold: {self._threshold}×)"
            ]
        return []


class LocaleNormalizer(_Stage):
    """
    Stage 4: Parse Indian number format → paise integer.

    Populates record.amount_paise from record.raw_amount_text.
    Also infers transaction_type from Dr/Cr suffix if not already set.
    """

    def run(self, record: RawTransaction) -> list[str]:
        # If amount_paise is already set (structured API source), skip parse
        if record.amount_paise is not None:
            return []

        if not record.raw_amount_text or not record.raw_amount_text.strip():
            return ["raw_amount_text is empty; cannot normalise amount"]

        try:
            paise = parse_inr_to_paise(record.raw_amount_text)
        except ValueError as exc:
            return [f"Cannot parse amount '{record.raw_amount_text}': {exc}"]

        # Apply sign based on transaction_type if amount is positive
        if record.transaction_type == "DEBIT" and paise > 0:
            paise = -paise
        elif record.transaction_type == "CREDIT" and paise < 0:
            paise = abs(paise)

        record.amount_paise = paise
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ValidationPipeline
# ─────────────────────────────────────────────────────────────────────────────

class ValidationPipeline:
    """
    Runs a RawTransaction through 4 sequential validation stages.

    Usage:
        pipeline = ValidationPipeline(spend_history=InMemorySpendHistory())
        result = pipeline.run(raw_tx)
        if result.passed:
            # use result.record
        else:
            # quarantine: result.failed_stage, result.errors
    """

    def __init__(self, spend_history: SpendHistoryPort) -> None:
        self._stages: list[tuple[str, _Stage]] = [
            ("SCHEMA", SchemaValidator()),
            ("RANGE", RangeValidator()),
            ("ANOMALY", AnomalyDetector(spend_history)),
            ("LOCALE", LocaleNormalizer()),
        ]

    def run(self, record: RawTransaction) -> PipelineResult:
        for stage_name, stage in self._stages:
            errors = stage.run(record)
            if errors:
                log.warning(
                    "validation_failed",
                    stage=stage_name,
                    owner_id=str(record.owner_id),
                    errors=errors,
                )
                return PipelineResult.fail(stage_name, errors)

        log.debug("validation_passed", owner_id=str(record.owner_id))
        return PipelineResult.pass_(record)
