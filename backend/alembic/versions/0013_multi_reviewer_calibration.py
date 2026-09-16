"""allow independent evaluator reviewers and explicit resolution roles

Revision ID: 0013_multi_reviewer_calibration
Revises: 0012_memory_capacity_reviews
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_multi_reviewer_calibration"
down_revision = "0012_memory_capacity_reviews"
branch_labels = None
depends_on = None


def upgrade():
    # Existing one-per-evaluation labels are the historical reference used by
    # the legacy endpoint.  Preserve that meaning before removing its unique
    # restriction, rather than reinterpreting old reviews as independent votes.
    op.add_column(
        "evaluation_human_reviews",
        sa.Column("review_role", sa.String(length=20), nullable=False, server_default="reference"),
    )
    op.add_column(
        "evaluation_human_reviews",
        sa.Column("based_on_review_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.drop_index("ix_evaluation_human_reviews_evaluation_id", table_name="evaluation_human_reviews")
    op.drop_constraint(
        "evaluation_human_reviews_evaluation_id_key",
        "evaluation_human_reviews",
        type_="unique",
    )
    op.create_index(
        "ix_evaluation_human_reviews_evaluation_id",
        "evaluation_human_reviews",
        ["evaluation_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_evaluation_human_review_reviewer_role",
        "evaluation_human_reviews",
        ["evaluation_id", "reviewer_label", "review_role"],
    )


def downgrade():
    # A downgrade is valid only if the caller first removes additional labels.
    # This intentionally avoids silently deleting independently collected data.
    op.drop_constraint(
        "uq_evaluation_human_review_reviewer_role",
        "evaluation_human_reviews",
        type_="unique",
    )
    op.drop_index("ix_evaluation_human_reviews_evaluation_id", table_name="evaluation_human_reviews")
    op.create_index(
        "ix_evaluation_human_reviews_evaluation_id",
        "evaluation_human_reviews",
        ["evaluation_id"],
        unique=True,
    )
    op.create_unique_constraint(
        "evaluation_human_reviews_evaluation_id_key",
        "evaluation_human_reviews",
        ["evaluation_id"],
    )
    op.drop_column("evaluation_human_reviews", "based_on_review_ids")
    op.drop_column("evaluation_human_reviews", "review_role")
