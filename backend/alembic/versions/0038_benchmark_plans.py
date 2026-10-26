"""Freeze Experiment C metadata without retaining benchmark sources.

Revision ID: 0038_benchmark_plans
Revises: 0037_agent_error_diagnostics
"""
from alembic import op
import sqlalchemy as sa
revision = '0038_benchmark_plans'
down_revision = '0037_agent_error_diagnostics'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('benchmark_plans',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('fingerprint_sha256', sa.String(64), nullable=False),
        sa.Column('protocol', sa.JSON(), nullable=False),
        sa.Column('executions', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('benchmark_plans')
