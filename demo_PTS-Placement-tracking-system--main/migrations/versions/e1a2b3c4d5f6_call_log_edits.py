"""call_log_edits table

Revision ID: e1a2b3c4d5f6
Revises: d5c1d7e9a3b0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e1a2b3c4d5f6"
down_revision = "d5c1d7e9a3b0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "call_log_edits" in set(inspect(bind).get_table_names()):
        return
    op.create_table(
        "call_log_edits",
        sa.Column("id", mysql.CHAR(32), primary_key=True),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("call_log_id", mysql.CHAR(32), nullable=False),
        sa.Column("candidate_id", mysql.CHAR(32), nullable=True),
        sa.Column("old_disposition_id", mysql.CHAR(32), nullable=True),
        sa.Column("new_disposition_id", mysql.CHAR(32), nullable=True),
        sa.Column("old_notes", sa.Text(), nullable=True),
        sa.Column("new_notes", sa.Text(), nullable=True),
        sa.Column("old_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("new_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("edited_by", mysql.CHAR(32), nullable=True),
        sa.Column("edited_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_call_log_edits_call_log_id", "call_log_edits", ["call_log_id"])
    op.create_index("ix_call_log_edits_organization_id", "call_log_edits", ["organization_id"])


def downgrade():
    op.drop_table("call_log_edits")