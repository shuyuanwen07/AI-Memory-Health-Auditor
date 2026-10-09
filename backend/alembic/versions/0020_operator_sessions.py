"""Revocable opaque operator access sessions."""
from alembic import op
import sqlalchemy as sa

revision = '0020_operator_sessions'
down_revision = '0019_replay_identity'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('operator_sessions',
        sa.Column('token_digest', sa.String(64), primary_key=True),
        sa.Column('credential_fingerprint', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_operator_sessions_expires_at', 'operator_sessions', ['expires_at'])


def downgrade():
    op.drop_index('ix_operator_sessions_expires_at', table_name='operator_sessions')
    op.drop_table('operator_sessions')
