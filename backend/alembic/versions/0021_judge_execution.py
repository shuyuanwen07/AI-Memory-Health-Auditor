"""Persist optional sanitised judge execution evidence without inventing historical costs."""
from alembic import op
import sqlalchemy as sa

revision = '0021_judge_execution'
down_revision = '0020_operator_sessions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('evaluation_results', sa.Column('judge_execution', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('evaluation_results', 'judge_execution')
