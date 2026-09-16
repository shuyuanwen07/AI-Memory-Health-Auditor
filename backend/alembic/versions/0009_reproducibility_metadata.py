"""add safe reproducibility metadata to runs and target responses

Revision ID: 0009_reproducibility_metadata
Revises: 0008_target_agent_memory_store
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_reproducibility_metadata"
down_revision = "0008_target_agent_memory_store"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_runs",
        sa.Column("reproducibility_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "target_responses",
        sa.Column("execution_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade():
    op.drop_column("target_responses", "execution_metadata")
    op.drop_column("audit_runs", "reproducibility_metadata")
