"""Add chat_sessions and agent_runs tables for Phase 2 multi-turn conversation.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── chat_sessions ──────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
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
    op.create_index("idx_chat_sessions_owner", "chat_sessions", ["owner_id"])

    # ── agent_runs ─────────────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("user_message", sa.Text, nullable=False),
        sa.Column("assistant_response", sa.Text, nullable=False),
        sa.Column("tool_calls", postgresql.JSONB, nullable=False),
        sa.Column("messages_trace", postgresql.JSONB, nullable=True),
        sa.Column("turn_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="OK"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_agent_runs_session", "agent_runs", ["session_id"])
    op.create_index("idx_agent_runs_owner", "agent_runs", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_runs_owner", table_name="agent_runs")
    op.drop_index("idx_agent_runs_session", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("idx_chat_sessions_owner", table_name="chat_sessions")
    op.drop_table("chat_sessions")
