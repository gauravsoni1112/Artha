"""Frontend enablement — auth columns on owners, preferences on user_profiles, family_memberships.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # owners — auth columns
    # ------------------------------------------------------------------
    op.add_column("owners", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("owners", sa.Column("pin_hash", sa.Text(), nullable=True))

    # ------------------------------------------------------------------
    # user_profiles — UI preferences
    # ------------------------------------------------------------------
    op.add_column(
        "user_profiles",
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    # ------------------------------------------------------------------
    # family_memberships
    # ------------------------------------------------------------------
    op.create_table(
        "family_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("family_id", "owner_id", name="uq_family_member"),
    )
    op.create_index("idx_family_memberships_family", "family_memberships", ["family_id"])
    op.create_index("idx_family_memberships_owner", "family_memberships", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_family_memberships_owner", table_name="family_memberships")
    op.drop_index("idx_family_memberships_family", table_name="family_memberships")
    op.drop_table("family_memberships")
    op.drop_column("user_profiles", "preferences")
    op.drop_column("owners", "pin_hash")
    op.drop_column("owners", "is_admin")
