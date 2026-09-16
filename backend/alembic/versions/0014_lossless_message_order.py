"""Keep externally supplied message IDs and their source order losslessly."""

from alembic import op
import sqlalchemy as sa

revision = "0014_lossless_message_order"
down_revision = "0013_multi_reviewer_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("source_message_id", sa.String(length=160), nullable=True))
    op.execute("UPDATE messages SET source_message_id = id WHERE source_message_id IS NULL")
    op.alter_column("messages", "source_message_id", nullable=False)
    op.add_column("messages", sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_messages_conversation_source_message_id", "messages", ["conversation_id", "source_message_id"])


def downgrade() -> None:
    op.drop_constraint("uq_messages_conversation_source_message_id", "messages", type_="unique")
    op.drop_column("messages", "sequence")
    op.drop_column("messages", "source_message_id")
