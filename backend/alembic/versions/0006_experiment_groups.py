"""add reproducible experiment groups and shared-suite references

Revision ID: 0006_experiment_groups
Revises: 0005_memory_strategy
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_experiment_groups"
down_revision = "0005_memory_strategy"
branch_labels = None
depends_on = None


def upgrade():
    # The source run is intentionally nullable: an Experiment exists before
    # its one canonical suite is generated.  It is set exactly once by the
    # route/service that creates that suite.
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(40),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="CREATED"),
        sa.Column("test_suite_configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("test_suite_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "test_suite_source_run_id",
            sa.String(40),
            sa.ForeignKey("audit_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_experiments_conversation_id", "experiments", ["conversation_id"])
    op.create_index("ix_experiments_test_suite_source_run_id", "experiments", ["test_suite_source_run_id"])
    # batch_alter_table keeps this migration runnable for local SQLite test
    # databases as well as PostgreSQL, where Alembic emits a normal ALTER.
    with op.batch_alter_table("audit_runs") as batch_op:
        batch_op.add_column(sa.Column("experiment_id", sa.String(40), nullable=True))
        batch_op.create_foreign_key(
            "fk_audit_runs_experiment_id",
            "experiments",
            ["experiment_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_audit_runs_experiment_id", "audit_runs", ["experiment_id"])
    with op.batch_alter_table("test_cases") as batch_op:
        batch_op.add_column(sa.Column("suite_test_id", sa.String(40), nullable=True))
        batch_op.create_foreign_key(
            "fk_test_cases_suite_test_id",
            "test_cases",
            ["suite_test_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_test_cases_suite_test_id", "test_cases", ["suite_test_id"])


def downgrade():
    op.drop_index("ix_test_cases_suite_test_id", table_name="test_cases")
    with op.batch_alter_table("test_cases") as batch_op:
        batch_op.drop_constraint("fk_test_cases_suite_test_id", type_="foreignkey")
        batch_op.drop_column("suite_test_id")
    op.drop_index("ix_audit_runs_experiment_id", table_name="audit_runs")
    with op.batch_alter_table("audit_runs") as batch_op:
        batch_op.drop_constraint("fk_audit_runs_experiment_id", type_="foreignkey")
        batch_op.drop_column("experiment_id")
    op.drop_index("ix_experiments_test_suite_source_run_id", table_name="experiments")
    op.drop_index("ix_experiments_conversation_id", table_name="experiments")
    op.drop_table("experiments")
