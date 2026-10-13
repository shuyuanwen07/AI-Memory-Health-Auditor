"""Add portable expiring locks for long-running non-PostgreSQL stages.

Revision ID: 0036_portable_stage_locks
Revises: 0035_conversation_source_origin
"""
from alembic import op
import sqlalchemy as sa


revision = "0036_portable_stage_locks"
down_revision = "0035_conversation_source_origin"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stage_locks",
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("owner_token", sa.String(length=40), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("scope"),
    )
    op.create_index("ix_stage_locks_owner_token", "stage_locks", ["owner_token"])
    op.create_index("ix_stage_locks_lease_expires_at", "stage_locks", ["lease_expires_at"])


def downgrade():
    op.drop_index("ix_stage_locks_lease_expires_at", table_name="stage_locks")
    op.drop_index("ix_stage_locks_owner_token", table_name="stage_locks")
    op.drop_table("stage_locks")
