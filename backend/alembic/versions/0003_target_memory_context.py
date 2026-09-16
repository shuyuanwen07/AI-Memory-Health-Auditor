"""store controlled target memory context

Revision ID: 0003_target_memory_context
Revises: 0002_target_provider
"""
from alembic import op
import sqlalchemy as sa
revision='0003_target_memory_context'; down_revision='0002_target_provider'; branch_labels=None; depends_on=None
def upgrade():
    op.add_column('test_cases', sa.Column('target_memory_context', sa.JSON(), nullable=False, server_default='[]'))
def downgrade():
    op.drop_column('test_cases', 'target_memory_context')
