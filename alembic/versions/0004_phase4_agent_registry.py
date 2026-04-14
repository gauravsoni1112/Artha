"""Phase 4 schema — agent_registry table for domain agent self-registration and routing.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_registry",
        sa.Column("agent_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("capabilities", postgresql.JSONB, nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("health_endpoint", sa.Text, nullable=False),
        sa.Column("timeout_ms", sa.Integer, nullable=False, server_default="10000"),
        sa.Column("fallback_strategy", sa.String(32), nullable=False, server_default="cached_response"),
        sa.Column("cache_ttl_hours", sa.Numeric(6, 2), nullable=False, server_default="1.0"),
        sa.Column("scope", sa.String(16), nullable=False, server_default="individual"),
        sa.Column("status", sa.String(16), nullable=False, server_default="HEALTHY"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_agent_registry_status", "agent_registry", ["status"])
    op.create_index("idx_agent_registry_scope", "agent_registry", ["scope"])


def downgrade() -> None:
    op.drop_index("idx_agent_registry_scope", table_name="agent_registry")
    op.drop_index("idx_agent_registry_status", table_name="agent_registry")
    op.drop_table("agent_registry")
