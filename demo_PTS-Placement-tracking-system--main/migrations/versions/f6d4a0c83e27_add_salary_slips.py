"""add salary_slips

Revision ID: f6d4a0c83e27
Revises: e5c3f9b72d16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "f6d4a0c83e27"
down_revision = "e5c3f9b72d16"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "salary_slips",
        sa.Column("id", mysql.CHAR(32), primary_key=True),
        sa.Column("candidate_id", mysql.CHAR(32), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "month", name="uq_salary_slip_candidate_month"),
    )
    op.create_index("ix_salary_slips_candidate_id", "salary_slips", ["candidate_id"])


def downgrade():
    op.drop_index("ix_salary_slips_candidate_id", table_name="salary_slips")
    op.drop_table("salary_slips")
