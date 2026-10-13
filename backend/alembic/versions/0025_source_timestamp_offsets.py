"""Retain original source offsets without guessing historical timezone data."""
from alembic import op
import sqlalchemy as sa

revision = '0025_source_timestamp_offsets'
down_revision = '0024_conversation_recovery'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('messages', sa.Column('original_timestamp', sa.String(80), nullable=True))


def downgrade():
    op.drop_column('messages', 'original_timestamp')
