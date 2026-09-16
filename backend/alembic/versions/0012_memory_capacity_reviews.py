"""freeze memory capacity and add evaluator calibration labels

Revision ID: 0012_memory_capacity_reviews
Revises: 0011_frozen_target_memory_writer
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_memory_capacity_reviews"
down_revision = "0011_frozen_target_memory_writer"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_runs",
        sa.Column("target_memory_capacity", sa.Integer(), nullable=False, server_default="50"),
    )
    op.create_table(
        "evaluation_human_reviews",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("run_id", sa.String(length=40), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluation_id", sa.String(length=40), sa.ForeignKey("evaluation_results.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("human_passed", sa.Boolean(), nullable=False),
        sa.Column("human_failure_type", sa.String(length=40), nullable=True),
        sa.Column("reviewer_label", sa.String(length=80), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_evaluation_human_reviews_run_id", "evaluation_human_reviews", ["run_id"])
    op.create_index("ix_evaluation_human_reviews_evaluation_id", "evaluation_human_reviews", ["evaluation_id"], unique=True)


def downgrade():
    op.drop_index("ix_evaluation_human_reviews_evaluation_id", table_name="evaluation_human_reviews")
    op.drop_index("ix_evaluation_human_reviews_run_id", table_name="evaluation_human_reviews")
    op.drop_table("evaluation_human_reviews")
    op.drop_column("audit_runs", "target_memory_capacity")
