"""Persist assessor comparisons without changing original audit evidence."""
from alembic import op
import sqlalchemy as sa

revision = '0026_assessor_comparisons'
down_revision = '0025_source_timestamp_offsets'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('assessor_comparisons',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('creation_request_key', sa.String(100), nullable=False, unique=True),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('source_run_id', sa.String(40), sa.ForeignKey('audit_runs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('runtime_signature', sa.JSON(), nullable=False),
        sa.Column('entries', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('assessor_comparisons')
