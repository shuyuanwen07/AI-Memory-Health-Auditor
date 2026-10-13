"""Bind new assessor plans to reference data without inventing legacy evidence."""
from alembic import op
import sqlalchemy as sa

revision = '0027_assessor_input_binding'
down_revision = '0026_assessor_comparisons'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assessor_comparisons', sa.Column('input_fingerprint', sa.String(64), nullable=True))


def downgrade():
    op.drop_column('assessor_comparisons', 'input_fingerprint')
