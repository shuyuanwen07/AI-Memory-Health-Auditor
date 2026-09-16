"""record experiment module identities

Revision ID: 0004_experiment_module_metadata
Revises: 0003_target_memory_context
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_experiment_module_metadata"
down_revision = "0003_target_memory_context"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_runs", sa.Column("pipeline_provider", sa.String(30), nullable=False, server_default="rule_based"))
    op.add_column("audit_runs", sa.Column("pipeline_model", sa.String(100), nullable=False, server_default="rule-based-v2"))
    op.add_column("audit_runs", sa.Column("evaluator_provider", sa.String(30), nullable=False, server_default="rule_based"))
    op.add_column("audit_runs", sa.Column("evaluator_model", sa.String(100), nullable=False, server_default="rule-based-v2"))


def downgrade():
    op.drop_column("audit_runs", "evaluator_model")
    op.drop_column("audit_runs", "evaluator_provider")
    op.drop_column("audit_runs", "pipeline_model")
    op.drop_column("audit_runs", "pipeline_provider")
