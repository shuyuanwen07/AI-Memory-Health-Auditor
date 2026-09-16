"""Enforce one directed relationship edge per memory at the database layer."""

from alembic import op

revision = "0015_relationship_integrity"
down_revision = "0014_lossless_message_order"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_unique_constraint("uq_memory_relationships_edge", "memory_relationships", ["memory_id", "relationship_type", "target_memory_id"])

def downgrade() -> None:
    op.drop_constraint("uq_memory_relationships_edge", "memory_relationships", type_="unique")
