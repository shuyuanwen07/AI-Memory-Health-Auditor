"""Durable single-variable test-generator comparisons."""
from alembic import op
import sqlalchemy as sa

revision = '0028_generator_comparisons'
down_revision = '0027_assessor_input_binding'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('generator_comparisons',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('creation_request_key', sa.String(100), nullable=False, unique=True),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('source_run_id', sa.String(40), sa.ForeignKey('audit_runs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('input_fingerprint', sa.String(64), nullable=False),
        sa.Column('runtime_signature', sa.JSON(), nullable=False),
        sa.Column('entries', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('generator_comparisons')
