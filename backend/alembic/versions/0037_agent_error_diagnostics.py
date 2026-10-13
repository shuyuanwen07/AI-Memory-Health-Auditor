"""Persist safe stage failure diagnostics for semantic agents.

Revision ID: 0037_agent_error_diagnostics
Revises: 0036_portable_stage_locks
"""
from alembic import op
import sqlalchemy as sa


revision = "0037_agent_error_diagnostics"
down_revision = "0036_portable_stage_locks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_executions", sa.Column("error_diagnostics", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("agent_executions", "error_diagnostics")
