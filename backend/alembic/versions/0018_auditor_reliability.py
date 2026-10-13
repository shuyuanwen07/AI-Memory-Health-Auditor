"""Keep uncertain automated decisions separate from pass/fail.

Revision ID: 0018_auditor_reliability
Revises: 0017_schema_contract_alignment
"""
from alembic import op
import sqlalchemy as sa
revision = "0018_auditor_reliability"
down_revision = "0017_schema_contract_alignment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_cases", sa.Column("probe_group_id", sa.String(40), nullable=True))
    op.add_column("test_cases", sa.Column("probe_variant", sa.String(40), nullable=True))
    with op.batch_alter_table("evaluation_results") as batch:
        batch.alter_column("passed", existing_type=sa.Boolean(), nullable=True)


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM evaluation_results WHERE passed IS NULL")).scalar():
        raise RuntimeError("Resolve uncertain verdicts before downgrading; no labels are silently rewritten.")
    with op.batch_alter_table("evaluation_results") as batch:
        batch.alter_column("passed", existing_type=sa.Boolean(), nullable=False)
    op.drop_column("test_cases", "probe_variant")
    op.drop_column("test_cases", "probe_group_id")
