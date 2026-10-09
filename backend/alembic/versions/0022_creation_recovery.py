"""Idempotent creation without changing historical audit identity."""
from alembic import op
import sqlalchemy as sa
revision = '0022_creation_recovery'
down_revision = '0021_judge_execution'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('experiments', 'audit_runs'):
        op.add_column(table, sa.Column('creation_request_key', sa.String(100), nullable=True))
        op.add_column(table, sa.Column('creation_request_fingerprint', sa.String(64), nullable=True))
        op.create_unique_constraint(f'uq_{table}_creation_request_key', table, ['creation_request_key'])


def downgrade():
    for table in ('audit_runs', 'experiments'):
        op.drop_constraint(f'uq_{table}_creation_request_key', table, type_='unique')
        op.drop_column(table, 'creation_request_fingerprint')
        op.drop_column(table, 'creation_request_key')
