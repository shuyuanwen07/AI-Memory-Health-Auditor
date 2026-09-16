"""add controlled target memory scopes and maintenance policy

Revision ID: 0010_memory_scopes
Revises: 0009_reproducibility_metadata
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_memory_scopes"
down_revision = "0009_reproducibility_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_runs",
        sa.Column(
            "memory_maintenance_policy", sa.String(40), nullable=False,
            server_default="update_aware_consolidation",
        ),
    )
    op.add_column(
        "target_agent_memories",
        sa.Column("scope", sa.String(40), nullable=False, server_default="episodic"),
    )
    op.create_index(
        "ix_target_agent_memories_run_id_scope", "target_agent_memories", ["run_id", "scope"]
    )


def downgrade():
    op.drop_index("ix_target_agent_memories_run_id_scope", table_name="target_agent_memories")
    op.drop_column("target_agent_memories", "scope")
    op.drop_column("audit_runs", "memory_maintenance_policy")
