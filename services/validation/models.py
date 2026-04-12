"""
RawTransaction — the Pydantic v2 input model for the ValidationPipeline.

A RawTransaction is the intermediate form produced by every parser before
validation. All fields that require parsing/normalisation are kept as raw
strings here so the pipeline stages can operate on them independently.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class RawTransaction(BaseModel):
    """
    Input to the ValidationPipeline.

    Parsers produce this; all monetary values are still raw strings.
    After Stage 4 (LocaleNormalizer), amount_paise is populated.
    """

    # Identity
    owner_id: uuid.UUID
    account_id: uuid.UUID

    # Date fields — parsers must provide a parsed date or a raw string
    transaction_date: date | None = None
    raw_date_text: str = ""          # original date string from PDF
    value_date: date | None = None

    # Amount — raw string from PDF; amount_paise is set after locale normalisation
    raw_amount_text: str = ""        # e.g. "1,00,000.50" or "500.00 Dr"
    amount_paise: int | None = None  # set by LocaleNormalizer
    transaction_type: str = ""       # CREDIT or DEBIT

    # Description
    raw_description: str = ""
    description: str = ""            # normalised description (set by normalizer)
    merchant: str | None = None
    category: str | None = None

    # Metadata
    currency: str = "INR"
    source_hash: str = ""            # set by IngestionService after validation
    document_id: uuid.UUID | None = None
    ingestion_run_id: uuid.UUID | None = None

    # Extra parser-specific fields (passed through to quarantine raw_data)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("transaction_type", mode="before")
    @classmethod
    def normalise_tx_type(cls, v: str) -> str:
        return v.upper().strip() if isinstance(v, str) else v

    @field_validator("currency", mode="before")
    @classmethod
    def normalise_currency(cls, v: str) -> str:
        return v.upper().strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def description_fallback(self) -> "RawTransaction":
        if not self.description and self.raw_description:
            self.description = self.raw_description.strip()
        return self


class PipelineResult(BaseModel):
    """Result returned by ValidationPipeline.run()."""

    passed: bool
    record: RawTransaction | None = None
    failed_stage: str | None = None   # SCHEMA / RANGE / ANOMALY / LOCALE
    errors: list[str] = Field(default_factory=list)

    @classmethod
    def pass_(cls, record: RawTransaction) -> "PipelineResult":
        return cls(passed=True, record=record)

    @classmethod
    def fail(cls, stage: str, errors: list[str]) -> "PipelineResult":
        return cls(passed=False, failed_stage=stage, errors=errors)
