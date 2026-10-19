"""data_breaches table

Revision ID: d4b0c6d8f2a9
Revises: d3a9b5c7e1f8
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "d4b0c6d8f2a9"
down_revision = "d3a9b5c7e1f8"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "data_breaches" in set(inspect(bind).get_table_names()):
        return
    op.create_table(
        "data_breaches",
        sa.Column("id", mysql.CHAR(32), primary_key=True),
        sa.Column("organization_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("occurred", sa.String(120), nullable=True),
        sa.Column("data_involved", sa.Text(), nullable=True),
        sa.Column("what_happened", sa.Text(), nullable=True),
        sa.Column("consequences", sa.Text(), nullable=True),
        sa.Column("measures", sa.Text(), nullable=True),
        sa.Column("advice", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(255), nullable=True),
        sa.Column("board_reported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recipients_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recipients_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", mysql.CHAR(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    pass