"""Persist the independently selected semantic-review model."""
from alembic import op
import sqlalchemy as sa


revision = "0031_agent_model_selection"
down_revision = "0030_model_availability"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_runs", sa.Column("semantic_review_provider", sa.String(30), nullable=True))
    op.add_column("audit_runs", sa.Column("semantic_review_model", sa.String(200), nullable=True))


def downgrade():
    op.drop_column("audit_runs", "semantic_review_model")
    op.drop_column("audit_runs", "semantic_review_provider")
