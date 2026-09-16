"""add test type and suite-quality metadata

Revision ID: 0007_test_quality_metadata
Revises: 0006_experiment_groups
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_test_quality_metadata"
down_revision = "0006_experiment_groups"
branch_labels = None
depends_on = None


def upgrade():
    # Defaults retain a readable value for all existing test cases until
    # experiment routes begin invoking the explicit validator.
    with op.batch_alter_table("test_cases") as batch_op:
        batch_op.add_column(sa.Column("test_type", sa.String(20), nullable=False, server_default="contextual"))
        batch_op.add_column(sa.Column("quality_status", sa.String(20), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("grounding_status", sa.String(20), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("validation_notes", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("test_cases") as batch_op:
        batch_op.drop_column("validation_notes")
        batch_op.drop_column("grounding_status")
        batch_op.drop_column("quality_status")
        batch_op.drop_column("test_type")
