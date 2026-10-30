"""Preserve derived benchmark analyses for Dashboard display.

Revision ID: 0039_benchmark_analyses
Revises: 0038_benchmark_plans
"""
from alembic import op
import sqlalchemy as sa

revision = '0039_benchmark_analyses'
down_revision = '0038_benchmark_plans'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('benchmark_analyses',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('plan_id', sa.String(40), sa.ForeignKey('benchmark_plans.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('report', sa.JSON(), nullable=False))
    op.create_index('ix_benchmark_analyses_plan_id', 'benchmark_analyses', ['plan_id'])

def downgrade():
    op.drop_index('ix_benchmark_analyses_plan_id', table_name='benchmark_analyses')
    op.drop_table('benchmark_analyses')
