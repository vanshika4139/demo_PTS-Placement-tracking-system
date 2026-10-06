"""add document reminder logs

Revision ID: d4b2e8a61c05
Revises: c3a1f9d27b10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "d4b2e8a61c05"
down_revision = "c3a1f9d27b10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_reminder_logs",
        sa.Column("id", mysql.CHAR(32), nullable=False),
        sa.Column("candidate_id", mysql.CHAR(32), nullable=False),
        sa.Column("reminder_day", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "reminder_day", name="uq_doc_reminder_candidate_day"),
    )
    op.create_index(
        "ix_document_reminder_logs_candidate_id",
        "document_reminder_logs", ["candidate_id"], unique=False,
    )


def downgrade():
    op.drop_index("ix_document_reminder_logs_candidate_id", table_name="document_reminder_logs")
    op.drop_table("document_reminder_logs")
