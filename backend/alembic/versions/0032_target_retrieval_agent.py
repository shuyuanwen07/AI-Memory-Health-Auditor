"""Persist the target-side memory retrieval Agent configuration."""
from alembic import op
import sqlalchemy as sa


revision = "0032_target_retrieval_agent"
down_revision = "0031_agent_model_selection"
branch_labels = None
depends_on = None


def upgrade():
    # Historical runs remain labelled as fixed retrieval. New audit creation
    # explicitly freezes the Agent choice in these columns.
    op.add_column("audit_runs", sa.Column("retrieval_mode", sa.String(20), nullable=False, server_default="fixed"))
    op.add_column("audit_runs", sa.Column("retrieval_provider", sa.String(30), nullable=True))
    op.add_column("audit_runs", sa.Column("retrieval_model", sa.String(200), nullable=True))


def downgrade():
    op.drop_column("audit_runs", "retrieval_model")
    op.drop_column("audit_runs", "retrieval_provider")
    op.drop_column("audit_runs", "retrieval_mode")
