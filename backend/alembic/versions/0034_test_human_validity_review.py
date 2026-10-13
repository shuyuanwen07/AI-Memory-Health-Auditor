"""Separate automated test quality from human validity review.

Revision ID: 0034_test_human_validity_review
Revises: 0033_agent_execution_evidence
"""
from alembic import op
import sqlalchemy as sa


revision = "0034_test_human_validity_review"
down_revision = "0033_agent_execution_evidence"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("test_cases") as batch_op:
        batch_op.add_column(sa.Column("human_validity_status", sa.String(20), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("human_validity_reviewer", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("human_validity_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("human_validity_reviewed_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("test_cases") as batch_op:
        batch_op.drop_column("human_validity_reviewed_at")
        batch_op.drop_column("human_validity_note")
        batch_op.drop_column("human_validity_reviewer")
        batch_op.drop_column("human_validity_status")
