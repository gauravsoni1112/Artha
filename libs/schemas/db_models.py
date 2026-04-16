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
    Float,
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
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pin_hash: Mapped[str | None] = mapped_column(Text, nullable=True)  # scrypt(PIN)
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
    chat_sessions: Mapped[list["ChatSession"]] = relationship("ChatSession", back_populates="owner")


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


class ChatSession(Base):
    """Persisted conversation session for multi-turn agent interactions."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)  # first 80 chars of first message
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")  # ACTIVE | CLOSED
    # Phase 3: summary of earlier turns written by context compaction
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["Owner"] = relationship("Owner", back_populates="chat_sessions")
    turns: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="session")

    __table_args__ = (Index("idx_chat_sessions_owner", "owner_id"),)


class AgentRun(Base):
    """One turn/request in a chat session — the agent's reasoning and response."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_response: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSONB, nullable=False)  # list of tool names invoked
    messages_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # full LangGraph trace
    # Phase 3: ReAct chain-of-thought — list of {"thought": str, "action": str} dicts
    scratchpad: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Phase 3: planner + reflection outputs
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reflection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OK")  # OK | ERROR
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="turns")

    __table_args__ = (
        Index("idx_agent_runs_session", "session_id"),
        Index("idx_agent_runs_owner", "owner_id"),
    )


class AgentRegistryEntry(Base):
    """
    Phase 4 — Domain agent registry.

    Agents self-register on startup by POSTing to the registry service.
    The router resolves capability → endpoint at dispatch time.

    INVARIANT: Only the registry service writes to this table.
    All other services treat it as read-only.
    """

    __tablename__ = "agent_registry"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False)  # list[str] e.g. ["cashflow","spending"]
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)          # e.g. http://cashflow_agent:8001
    health_endpoint: Mapped[str] = mapped_column(Text, nullable=False)   # e.g. http://cashflow_agent:8001/health
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    fallback_strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="cached_response"
    )  # cached_response | skip | error
    cache_ttl_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=1.0)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="individual")  # individual | family
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="HEALTHY")    # HEALTHY | DEGRADED | DOWN
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_agent_registry_status", "status"),
        Index("idx_agent_registry_scope", "scope"),
    )


# ---------------------------------------------------------------------------
# Phase 5 — Planner + Critic
# ---------------------------------------------------------------------------


class UserProfile(Base):
    """
    Persistent user profile — source of truth for Planner access scoping.

    Agents NEVER read this table directly; the orchestrator builds a
    UserProfileSnapshot and injects it into every AgentRequest.
    """

    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False, unique=True
    )
    risk_appetite: Mapped[str] = mapped_column(
        String(16), nullable=False, default="moderate"
    )  # conservative | moderate | aggressive
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_family_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # UI prefs
    # Denormalised totals — kept in sync by the orchestrator, not by agents.
    total_monthly_income_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    income_sources_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    emis_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    scopes: Mapped[list["UserProfileScope"]] = relationship(
        "UserProfileScope", back_populates="profile"
    )
    snapshots: Mapped[list["UserProfileSnapshot"]] = relationship(
        "UserProfileSnapshot", back_populates="profile"
    )

    __table_args__ = (Index("idx_user_profiles_owner", "owner_id"),)


class UserProfileScope(Base):
    """
    Maps a UserProfile to the owner_ids it may access, with their scope role.
    Created by the orchestrator; never written by agents.

    Example: profile for owner A grants PRIMARY access to A,
             SPOUSE access to owner B, DEPENDENT to C.
    """

    __tablename__ = "user_profile_scopes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # AccessScope enum
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="scopes")

    __table_args__ = (
        UniqueConstraint("profile_id", "owner_id", name="uq_profile_scope_owner"),
        Index("idx_profile_scopes_profile", "profile_id"),
    )


class UserProfileSnapshot(Base):
    """
    Immutable point-in-time copy of a UserProfile.
    Every Recommendation stores a snapshot_id so audit log is reproducible
    even after the live profile changes.

    INVARIANT: never update or delete rows in this table.
    """

    __tablename__ = "user_profile_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id"), nullable=False
    )
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)  # serialised UserProfile
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="snapshots")
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="snapshot"
    )

    __table_args__ = (Index("idx_snapshots_profile", "profile_id"),)


class Recommendation(Base):
    """
    Immutable recommendation header — written once at plan completion.

    current_state is a denormalized cache of the latest event_type for
    efficient queries.  The recommendation_events table is authoritative.

    INVARIANT: append-only. Never UPDATE this row after insert.
    """

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profile_snapshots.id"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False)          # serialised Plan DAG
    agent_outputs_json: Mapped[list] = mapped_column(JSONB, nullable=False) # full agent I/O for replay
    final_output_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    composite_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    current_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="GENERATED"
    )  # RecommendationState — denormalized
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    snapshot: Mapped["UserProfileSnapshot"] = relationship(
        "UserProfileSnapshot", back_populates="recommendations"
    )
    events: Mapped[list["RecommendationEvent"]] = relationship(
        "RecommendationEvent", back_populates="recommendation", order_by="RecommendationEvent.created_at"
    )

    __table_args__ = (
        Index("idx_recommendations_owner", "owner_id"),
        Index("idx_recommendations_state", "current_state"),
        Index("idx_recommendations_snapshot", "snapshot_id"),
    )


class RecommendationEvent(Base):
    """
    Append-only audit log for recommendation state transitions.

    Every state change (surfaced, accepted, rejected, …) is a new row.
    Rows are never updated or deleted.
    actor_user_id is NULL only for the initial GENERATED event.
    """

    __tablename__ = "recommendation_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendations.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # RecommendationState
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    recommendation: Mapped["Recommendation"] = relationship(
        "Recommendation", back_populates="events"
    )

    __table_args__ = (
        Index("idx_rec_events_recommendation", "recommendation_id"),
        Index("idx_rec_events_type", "event_type"),
    )


# ---------------------------------------------------------------------------
# Phase 6 (frontend enablement) — family memberships + auth columns
# ---------------------------------------------------------------------------


class FamilyMembership(Base):
    """
    Lightweight family grouping.  The primary owner's id doubles as family_id.
    Any family member with is_admin=True can manage static data for all members
    in the same family.

    role: PRIMARY | SPOUSE | DEPENDENT
    """

    __tablename__ = "family_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )  # primary owner's id acts as family group key
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # PRIMARY | SPOUSE | DEPENDENT
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("family_id", "owner_id", name="uq_family_member"),
        Index("idx_family_memberships_family", "family_id"),
        Index("idx_family_memberships_owner", "owner_id"),
    )
