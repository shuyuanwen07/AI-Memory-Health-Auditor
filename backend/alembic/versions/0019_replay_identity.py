"""Separate cross-study comparison identity from editable local suite identity."""
from alembic import op
import sqlalchemy as sa
revision = "0019_replay_identity"
down_revision = "0018_auditor_reliability"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_cases", sa.Column("comparison_test_id", sa.String(40), nullable=True))


def downgrade():
    op.drop_column("test_cases", "comparison_test_id")
