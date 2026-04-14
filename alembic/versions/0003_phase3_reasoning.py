"""Phase 3 schema additions — ReAct scratchpad, confidence scoring, reflection, context compaction.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── agent_runs: Phase 3 reasoning columns ─────────────────────────
    # 3.1 — ReAct chain-of-thought scratchpad
    op.add_column(
        "agent_runs",
        sa.Column("scratchpad", postgresql.JSONB, nullable=True),
    )
    # 3.3 — reflection outputs
    op.add_column(
        "agent_runs",
        sa.Column("confidence_score", sa.Float, nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("reflection_notes", sa.Text, nullable=True),
    )

    # ── chat_sessions: context compaction summary ──────────────────────
    # 3.6 — summary of compacted earlier turns
    op.add_column(
        "chat_sessions",
        sa.Column("summary", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "summary")
    op.drop_column("agent_runs", "reflection_notes")
    op.drop_column("agent_runs", "confidence_score")
    op.drop_column("agent_runs", "scratchpad")
