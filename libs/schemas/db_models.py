"""
SQLAlchemy 2.0 ORM models for Artha.

INVARIANTS:
- All monetary columns are BIGINT (paise), never Float/Numeric.
- source_hash is the idempotency key for transactions — never weakened.
- transactions_quarantine has NO foreign key FROM transactions.
- PAN and account numbers are stored as SHA-256 hashes only.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    pan_hash: Mapped[str | None] = mapped_column(Text, nullable=True)  # SHA-256(PAN)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="owner")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="owner")
    holdings: Mapped[list["Holding"]] = relationship("Holding", back_populates="owner")
    goals: Mapped[list["FinancialGoal"]] = relationship("FinancialGoal", back_populates="owner")
    tax_records: Mapped[list["TaxData"]] = relationship("TaxData", back_populates="owner")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    account_number_hash: Mapped[str | None] = mapped_column(Text, nullable=True)  # SHA-256
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    owner: Mapped["Owner"] = relationship("Owner", back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="account")
    holdings: Mapped[list["Holding"]] = relationship("Holding", back_populates="account")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)       # IngestionSource
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)     # DocumentType
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # SHA-256; dedup
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="document")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)  # SCHEDULED / ADHOC
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="ingestion_run"
    )
    quarantine_records: Mapped[list["TransactionQuarantine"]] = relationship(
        "TransactionQuarantine", back_populates="ingestion_run"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    source_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # INVARIANT: amount_paise is BIGINT (paise), never float. Signed: positive=credit, negative=debit.
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(16), nullable=False)  # CREDIT / DEBIT
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    merchant: Mapped[str | None] = mapped_column(Text, nullable=True)
    fiscal_year: Mapped[str] = mapped_column(String(8), nullable=False)  # "2024-25"
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    owner: Mapped["Owner"] = relationship("Owner", back_populates="transactions")
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")
    document: Mapped["Document | None"] = relationship("Document", back_populates="transactions")
    ingestion_run: Mapped["IngestionRun | None"] = relationship(
        "IngestionRun", back_populates="transactions"
    )

    __table_args__ = (
        Index("idx_transactions_owner_date", "owner_id", "transaction_date"),
        Index("idx_transactions_account", "account_id"),
        Index("idx_transactions_fiscal_year", "fiscal_year"),
        Index("idx_transactions_category", "category"),
    )


class Holding(Base):
    """Non-transaction assets: MF units, equity, insurance, real estate, gold, FD, PPF, NPS."""

    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True
    )
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_name: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    units: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    # All paise values are BIGINT — no float.
    nav_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    purchase_price_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_value_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    valuation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["Owner"] = relationship("Owner", back_populates="holdings")
    account: Mapped["Account | None"] = relationship("Account", back_populates="holdings")


class FinancialGoal(Base):
    __tablename__ = "financial_goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    goal_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["Owner"] = relationship("Owner", back_populates="goals")


class TaxData(Base):
    """ITR summary per owner per fiscal year."""

    __tablename__ = "tax_data"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    fiscal_year: Mapped[str] = mapped_column(String(8), nullable=False)
    gross_income_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    taxable_income_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tax_paid_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tds_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    itr_filed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    owner: Mapped["Owner"] = relationship("Owner", back_populates="tax_records")

    __table_args__ = (UniqueConstraint("owner_id", "fiscal_year", name="uq_tax_data_owner_fy"),)


class TransactionQuarantine(Base):
    """
    Dead-end table for records that failed validation.

    INVARIANT: Downstream analytical agents MUST NEVER query this table.
    There is intentionally no FK from Transaction to TransactionQuarantine.
    """

    __tablename__ = "transactions_quarantine"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    failure_stage: Mapped[str] = mapped_column(String(16), nullable=False)   # SCHEMA/RANGE/ANOMALY/LOCALE
    failure_reasons: Mapped[list] = mapped_column(JSONB, nullable=False)
    raw_amount_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_date_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quarantine_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING_REVIEW"
    )
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ingestion_run: Mapped["IngestionRun | None"] = relationship(
        "IngestionRun", back_populates="quarantine_records"
    )

    __table_args__ = (
        Index("idx_quarantine_status", "quarantine_status"),
        Index("idx_quarantine_run", "ingestion_run_id"),
    )
