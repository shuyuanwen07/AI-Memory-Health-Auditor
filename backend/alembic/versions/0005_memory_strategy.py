"""record controlled memory strategy

Revision ID: 0005_memory_strategy
Revises: 0004_experiment_module_metadata
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_memory_strategy"
down_revision = "0004_experiment_module_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_runs", sa.Column("memory_strategy", sa.String(40), nullable=False, server_default="strong_rule_based"))


def downgrade():
    op.drop_column("audit_runs", "memory_strategy")
