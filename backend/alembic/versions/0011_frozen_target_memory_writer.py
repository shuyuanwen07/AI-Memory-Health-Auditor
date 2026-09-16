"""freeze target memory writer settings on each audit run

Revision ID: 0011_frozen_target_memory_writer
Revises: 0010_memory_scopes
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_frozen_target_memory_writer"
down_revision = "0010_memory_scopes"
branch_labels = None
depends_on = None


def upgrade():
    # Existing Foundation runs used the deterministic writer.  Backfilling
    # that explicit fact ensures they remain readable and reproducible after
    # operators change TARGET_MEMORY_WRITER for later experiments.
    op.add_column(
        "audit_runs",
        sa.Column(
            "target_memory_writer", sa.String(40), nullable=False,
            server_default="rule_based",
        ),
    )
    op.add_column(
        "audit_runs",
        sa.Column(
            "target_memory_writer_version", sa.String(100), nullable=True,
            server_default="rule-based-memory-extractor-v1",
        ),
    )


def downgrade():
    op.drop_column("audit_runs", "target_memory_writer_version")
    op.drop_column("audit_runs", "target_memory_writer")
