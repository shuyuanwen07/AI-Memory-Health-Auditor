"""Preserve conversation identity after interrupted intake responses."""
from alembic import op
import sqlalchemy as sa
revision = '0024_conversation_recovery'
down_revision = '0023_observed_failure'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversations', sa.Column('creation_request_key', sa.String(100), nullable=True))
    op.add_column('conversations', sa.Column('creation_request_fingerprint', sa.String(64), nullable=True))
    op.create_unique_constraint('uq_conversations_creation_request_key', 'conversations', ['creation_request_key'])


def downgrade():
    op.drop_constraint('uq_conversations_creation_request_key', 'conversations', type_='unique')
    op.drop_column('conversations', 'creation_request_fingerprint')
    op.drop_column('conversations', 'creation_request_key')
