"""Keep historical test-dimension labels distinct from observed error diagnoses."""
from alembic import op
import sqlalchemy as sa

revision = '0023_observed_failure'
down_revision = '0022_creation_recovery'
branch_labels = None
depends_on = None


def upgrade():
    # NULL identifies historical records. Do not invent diagnoses or rewrite
    # the original labels: the API marks them as legacy and excludes their type.
    op.add_column('evaluation_results', sa.Column('failure_classification', sa.JSON(), nullable=True))
    op.add_column('conversations', sa.Column('extraction_provenance', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('conversations', 'extraction_provenance')
    op.drop_column('evaluation_results', 'failure_classification')
