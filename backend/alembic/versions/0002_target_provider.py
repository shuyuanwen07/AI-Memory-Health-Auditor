"""add selectable target provider

Revision ID: 0002_target_provider
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
revision='0002_target_provider'; down_revision='0001_initial'; branch_labels=None; depends_on=None
def upgrade():
    op.add_column('audit_runs', sa.Column('provider', sa.String(30), nullable=False, server_default='rule_based'))
def downgrade():
    op.drop_column('audit_runs', 'provider')
