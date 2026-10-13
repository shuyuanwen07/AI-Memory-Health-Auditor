"""Persist the declared origin category for imported conversation data.

Revision ID: 0035_conversation_source_origin
Revises: 0034_test_human_validity_review
"""
from alembic import op
import sqlalchemy as sa


revision = "0035_conversation_source_origin"
down_revision = "0034_test_human_validity_review"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("source_origin", sa.String(length=24), nullable=False, server_default="unknown"))
    # The saved source and approval are explicitly recorded as synthetic in
    # the implementation evidence. Bind that one known operational smoke to
    # its origin; leave every other historical row unknown rather than infer.
    op.execute(sa.text(
        "UPDATE conversations SET source_origin = 'synthetic' "
        "WHERE id IN (SELECT conversation_id FROM audit_runs WHERE id = :run_id)"
    ).bindparams(run_id="RUN33F698DCBA6E4DABB8E4BAFB37002D44"))


def downgrade():
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("source_origin")
