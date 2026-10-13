"""Credential-scoped real model availability checks, without stored keys."""
from alembic import op
import sqlalchemy as sa

revision='0030_model_availability'
down_revision='0029_extraction_comparisons'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('model_availability',sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('model',sa.String(200),nullable=False),sa.Column('credential_scope',sa.String(64),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('operations',sa.JSON(),nullable=False),
        sa.Column('checked_at',sa.DateTime(),nullable=True))
    op.create_index('ix_model_availability_model','model_availability',['model'])
    op.create_index('ix_model_availability_credential_scope','model_availability',['credential_scope'])


def downgrade():
    op.drop_table('model_availability')
