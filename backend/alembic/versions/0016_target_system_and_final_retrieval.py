"""Persist the system-under-test adapter and final retrieval attribution."""

from alembic import op
import sqlalchemy as sa


# ``alembic_version.version_num`` is VARCHAR(32) in the initial schema.
# Keep revision identifiers within that durable constraint.
revision = "0016_target_system_retrieval"
down_revision = "0015_relationship_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_runs", sa.Column(
        "target_system_adapter", sa.String(length=60), nullable=False,
        server_default="controlled-memory",
    ))
    op.add_column("audit_runs", sa.Column(
        "target_system_adapter_version", sa.String(length=100), nullable=True,
        server_default="controlled-memory-v1",
    ))
    op.add_column("target_agent_retrievals", sa.Column(
        "final_response_id", sa.String(length=40), nullable=True,
    ))
    op.create_foreign_key(
        "fk_target_agent_retrievals_final_response", "target_agent_retrievals",
        "target_responses", ["final_response_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "ix_target_agent_retrievals_final_response_id", "target_agent_retrievals", ["final_response_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_target_agent_retrievals_final_response_id", table_name="target_agent_retrievals")
    op.drop_constraint("fk_target_agent_retrievals_final_response", "target_agent_retrievals", type_="foreignkey")
    op.drop_column("target_agent_retrievals", "final_response_id")
    op.drop_column("audit_runs", "target_system_adapter_version")
    op.drop_column("audit_runs", "target_system_adapter")
