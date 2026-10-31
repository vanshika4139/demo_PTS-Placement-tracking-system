"""communication_transactions and notification_retries

Revision ID: e8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "communication_transactions" not in tables:
        op.create_table(
            "communication_transactions",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), nullable=False),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("change", sa.Integer(), nullable=False),
            sa.Column("balance_before", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(60), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_comm_tx_org", "communication_transactions", ["organization_id"])
        op.create_index("ix_comm_tx_created", "communication_transactions", ["created_at"])
    if "notification_retries" not in tables:
        op.create_table(
            "notification_retries",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), nullable=True),
            sa.Column("candidate_id", mysql.CHAR(32), nullable=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("recipient", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(255), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_notif_retry_status", "notification_retries", ["status"])
        op.create_index("ix_notif_retry_next", "notification_retries", ["next_attempt_at"])
        op.create_index("ix_notif_retry_org", "notification_retries", ["organization_id"])


def downgrade():
    pass