"""candidate_consents table and support_tickets.request_type

Revision ID: d3a9b5c7e1f8
Revises: d2f8a4b6c0e7
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "d3a9b5c7e1f8"
down_revision = "d2f8a4b6c0e7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "candidate_consents" not in tables:
        op.create_table(
            "candidate_consents",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("candidate_id", mysql.CHAR(32), nullable=False),
            sa.Column("organization_id", sa.BigInteger(), nullable=True),
            sa.Column("notice_version", sa.String(20), nullable=False),
            sa.Column("consented_at", sa.DateTime(), nullable=False),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_candidate_consents_candidate_id", "candidate_consents", ["candidate_id"])

    if "support_tickets" in tables:
        cols = {c["name"] for c in insp.get_columns("support_tickets")}
        if "request_type" not in cols:
            op.add_column("support_tickets", sa.Column("request_type", sa.String(30), nullable=True))


def downgrade():
    pass