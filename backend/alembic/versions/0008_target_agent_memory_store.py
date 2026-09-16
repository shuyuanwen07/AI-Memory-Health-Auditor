"""add persistent private target-agent memory store

Revision ID: 0008_target_agent_memory_store
Revises: 0007_test_quality_metadata
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_target_agent_memory_store"
down_revision = "0007_test_quality_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "target_agent_memories",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_conversation_id", sa.String(40), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_value", sa.Text(), nullable=False),
        sa.Column("lifecycle_state", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("source_message_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("write_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_target_agent_memories_run_id", "target_agent_memories", ["run_id"])
    op.create_index("ix_target_agent_memories_source_conversation_id", "target_agent_memories", ["source_conversation_id"])

    op.create_table(
        "target_agent_memory_relationships",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_id", sa.String(40), sa.ForeignKey("target_agent_memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("target_memory_id", sa.String(40), sa.ForeignKey("target_agent_memories.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_target_agent_memory_relationships_run_id", "target_agent_memory_relationships", ["run_id"])
    op.create_index("ix_target_agent_memory_relationships_memory_id", "target_agent_memory_relationships", ["memory_id"])
    op.create_index("ix_target_agent_memory_relationships_target_memory_id", "target_agent_memory_relationships", ["target_memory_id"])

    op.create_table(
        "target_agent_memory_events",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_id", sa.String(40), sa.ForeignKey("target_agent_memories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("source_message_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_target_agent_memory_events_run_id", "target_agent_memory_events", ["run_id"])
    op.create_index("ix_target_agent_memory_events_memory_id", "target_agent_memory_events", ["memory_id"])

    op.create_table(
        "target_agent_retrievals",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_id", sa.String(40), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy", sa.String(40), nullable=False),
        sa.Column("selected_memory_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("ranking_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_target_agent_retrievals_run_id", "target_agent_retrievals", ["run_id"])
    op.create_index("ix_target_agent_retrievals_test_id", "target_agent_retrievals", ["test_id"])


def downgrade():
    op.drop_index("ix_target_agent_retrievals_test_id", table_name="target_agent_retrievals")
    op.drop_index("ix_target_agent_retrievals_run_id", table_name="target_agent_retrievals")
    op.drop_table("target_agent_retrievals")
    op.drop_index("ix_target_agent_memory_events_memory_id", table_name="target_agent_memory_events")
    op.drop_index("ix_target_agent_memory_events_run_id", table_name="target_agent_memory_events")
    op.drop_table("target_agent_memory_events")
    op.drop_index("ix_target_agent_memory_relationships_target_memory_id", table_name="target_agent_memory_relationships")
    op.drop_index("ix_target_agent_memory_relationships_memory_id", table_name="target_agent_memory_relationships")
    op.drop_index("ix_target_agent_memory_relationships_run_id", table_name="target_agent_memory_relationships")
    op.drop_table("target_agent_memory_relationships")
    op.drop_index("ix_target_agent_memories_source_conversation_id", table_name="target_agent_memories")
    op.drop_index("ix_target_agent_memories_run_id", table_name="target_agent_memories")
    op.drop_table("target_agent_memories")
