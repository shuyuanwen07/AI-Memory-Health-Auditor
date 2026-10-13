"""Persist evidence and trace metadata for semantic-agent roles.

Revision ID: 0033_agent_execution_evidence
Revises: 0032_target_retrieval_agent
"""
from alembic import op
import sqlalchemy as sa


revision = "0033_agent_execution_evidence"
down_revision = "0032_target_retrieval_agent"
branch_labels = None
depends_on = None


def upgrade():
    # Null preserves the meaning of historical model and manually entered data.
    op.add_column("memories", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("memory_relationships", sa.Column("evidence_message_ids", sa.JSON(), nullable=True))
    op.add_column("memory_relationships", sa.Column("confidence", sa.Float(), nullable=True))
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("conversation_id", sa.String(40), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("reported_model", sa.String(200), nullable=True),
        sa.Column("prompt_template_version", sa.String(100), nullable=False),
        sa.Column("prompt_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_summary", sa.String(500), nullable=True),
        sa.Column("handoff_from", sa.String(40), nullable=True),
        sa.Column("handoff_to", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_executions_role", "agent_executions", ["role"])
    op.create_index("ix_agent_executions_conversation_id", "agent_executions", ["conversation_id"])
    op.create_index("ix_agent_executions_run_id", "agent_executions", ["run_id"])


def downgrade():
    op.drop_index("ix_agent_executions_run_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_conversation_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_role", table_name="agent_executions")
    op.drop_table("agent_executions")
    op.drop_column("memory_relationships", "confidence")
    op.drop_column("memory_relationships", "evidence_message_ids")
    op.drop_column("memories", "confidence")
