"""Align declared ORM indexes and named constraints with the migration chain.

Revision ID: 0017_schema_contract_alignment
Revises: 0016_target_system_retrieval
"""

from alembic import op


revision = "0017_schema_contract_alignment"
down_revision = "0016_target_system_retrieval"
branch_labels = None
depends_on = None


_INDEXES = (
    ("ix_audit_runs_conversation_id", "audit_runs", ["conversation_id"]),
    ("ix_evaluation_results_test_id", "evaluation_results", ["test_id"]),
    ("ix_memories_conversation_id", "memories", ["conversation_id"]),
    ("ix_messages_conversation_id", "messages", ["conversation_id"]),
    ("ix_target_responses_run_id", "target_responses", ["run_id"]),
    ("ix_target_responses_test_id", "target_responses", ["test_id"]),
    ("ix_test_cases_run_id", "test_cases", ["run_id"]),
)


def upgrade() -> None:
    # These foreign-key access paths are already declared using ``index=True``
    # in the ORM. Earlier Foundation migrations predated that convention.
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
