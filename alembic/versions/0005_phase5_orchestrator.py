"""Phase 5 schema — user profiles, snapshots, recommendations, and recommendation events.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # user_profiles
    # ------------------------------------------------------------------
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column("risk_appetite", sa.String(16), nullable=False, server_default="moderate"),
        sa.Column("age", sa.Integer, nullable=True),
        sa.Column("is_family_scope", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("total_monthly_income_paise", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("income_sources_json", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("emis_json", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint("owner_id", name="uq_user_profiles_owner"),
    )
    op.create_index("idx_user_profiles_owner", "user_profiles", ["owner_id"])

    # ------------------------------------------------------------------
    # user_profile_scopes
    # ------------------------------------------------------------------
    op.create_table(
        "user_profile_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("profile_id", "owner_id", name="uq_profile_scope_owner"),
    )
    op.create_index("idx_profile_scopes_profile", "user_profile_scopes", ["profile_id"])

    # ------------------------------------------------------------------
    # user_profile_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "user_profile_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id"),
            nullable=False,
        ),
        sa.Column("snapshot_json", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_snapshots_profile", "user_profile_snapshots", ["profile_id"])

    # ------------------------------------------------------------------
    # recommendations
    # ------------------------------------------------------------------
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profile_snapshots.id"),
            nullable=False,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("plan_json", postgresql.JSONB, nullable=False),
        sa.Column("agent_outputs_json", postgresql.JSONB, nullable=False),
        sa.Column("final_output_json", postgresql.JSONB, nullable=False),
        sa.Column("composite_confidence", sa.Float, nullable=False),
        sa.Column("current_state", sa.String(32), nullable=False, server_default="GENERATED"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_recommendations_owner", "recommendations", ["owner_id"])
    op.create_index("idx_recommendations_state", "recommendations", ["current_state"])
    op.create_index("idx_recommendations_snapshot", "recommendations", ["snapshot_id"])

    # ------------------------------------------------------------------
    # recommendation_events
    # ------------------------------------------------------------------
    op.create_table(
        "recommendation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_rec_events_recommendation", "recommendation_events", ["recommendation_id"])
    op.create_index("idx_rec_events_type", "recommendation_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("idx_rec_events_type", table_name="recommendation_events")
    op.drop_index("idx_rec_events_recommendation", table_name="recommendation_events")
    op.drop_table("recommendation_events")

    op.drop_index("idx_recommendations_snapshot", table_name="recommendations")
    op.drop_index("idx_recommendations_state", table_name="recommendations")
    op.drop_index("idx_recommendations_owner", table_name="recommendations")
    op.drop_table("recommendations")

    op.drop_index("idx_snapshots_profile", table_name="user_profile_snapshots")
    op.drop_table("user_profile_snapshots")

    op.drop_index("idx_profile_scopes_profile", table_name="user_profile_scopes")
    op.drop_table("user_profile_scopes")

    op.drop_index("idx_user_profiles_owner", table_name="user_profiles")
    op.drop_table("user_profiles")
