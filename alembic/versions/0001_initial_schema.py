"""Initial schema — all Phase 1 tables

Revision ID: 0001
Revises:
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ── owners ──────────────────────────────────────────────────────
    op.create_table(
        "owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("pan_hash", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── accounts ────────────────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("institution", sa.Text, nullable=False),
        sa.Column("account_number_hash", sa.Text, nullable=True),
        sa.Column("nickname", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── documents ───────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=True,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_hash", sa.Text, nullable=False, unique=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parse_status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── ingestion_runs ──────────────────────────────────────────────
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.Column("records_fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_passed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_quarantined", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    # ── transactions ────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("source_hash", sa.Text, nullable=False, unique=True),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date, nullable=True),
        sa.Column("amount_paise", sa.BigInteger, nullable=False),  # INVARIANT: never Float
        sa.Column("transaction_type", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("raw_description", sa.Text, nullable=False),
        sa.Column("merchant", sa.Text, nullable=True),
        sa.Column("fiscal_year", sa.String(8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_transactions_owner_date", "transactions", ["owner_id", "transaction_date"])
    op.create_index("idx_transactions_account", "transactions", ["account_id"])
    op.create_index("idx_transactions_fiscal_year", "transactions", ["fiscal_year"])
    op.create_index("idx_transactions_category", "transactions", ["category"])

    # ── holdings ────────────────────────────────────────────────────
    op.create_table(
        "holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=True,
        ),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("instrument_name", sa.Text, nullable=False),
        sa.Column("isin", sa.String(12), nullable=True),
        sa.Column("units", sa.Numeric(20, 4), nullable=True),
        sa.Column("nav_paise", sa.BigInteger, nullable=True),
        sa.Column("purchase_price_paise", sa.BigInteger, nullable=True),
        sa.Column("current_value_paise", sa.BigInteger, nullable=True),
        sa.Column("valuation_date", sa.Date, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── financial_goals ─────────────────────────────────────────────
    op.create_table(
        "financial_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("goal_name", sa.Text, nullable=False),
        sa.Column("target_amount_paise", sa.BigInteger, nullable=False),
        sa.Column("current_amount_paise", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── tax_data ────────────────────────────────────────────────────
    op.create_table(
        "tax_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.String(8), nullable=False),
        sa.Column("gross_income_paise", sa.BigInteger, nullable=True),
        sa.Column("taxable_income_paise", sa.BigInteger, nullable=True),
        sa.Column("tax_paid_paise", sa.BigInteger, nullable=True),
        sa.Column("tds_paise", sa.BigInteger, nullable=True),
        sa.Column("itr_filed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("owner_id", "fiscal_year", name="uq_tax_data_owner_fy"),
    )

    # ── transactions_quarantine ─────────────────────────────────────
    # INVARIANT: agents MUST NEVER query this table.
    # There is intentionally no FK from transactions to this table.
    op.create_table(
        "transactions_quarantine",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column("raw_data", postgresql.JSONB, nullable=False),
        sa.Column("failure_stage", sa.String(16), nullable=False),
        sa.Column("failure_reasons", postgresql.JSONB, nullable=False),
        sa.Column("raw_amount_text", sa.Text, nullable=True),
        sa.Column("raw_date_text", sa.Text, nullable=True),
        sa.Column(
            "quarantine_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column("resolved_by", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_quarantine_status", "transactions_quarantine", ["quarantine_status"])
    op.create_index("idx_quarantine_run", "transactions_quarantine", ["ingestion_run_id"])


def downgrade() -> None:
    op.drop_table("transactions_quarantine")
    op.drop_table("tax_data")
    op.drop_table("financial_goals")
    op.drop_table("holdings")
    op.drop_index("idx_transactions_category", table_name="transactions")
    op.drop_index("idx_transactions_fiscal_year", table_name="transactions")
    op.drop_index("idx_transactions_account", table_name="transactions")
    op.drop_index("idx_transactions_owner_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("ingestion_runs")
    op.drop_table("documents")
    op.drop_table("accounts")
    op.drop_table("owners")
