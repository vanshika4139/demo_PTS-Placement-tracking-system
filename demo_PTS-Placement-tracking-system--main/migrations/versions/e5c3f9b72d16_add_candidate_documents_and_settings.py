"""add candidate documents and document settings

Revision ID: e5c3f9b72d16
Revises: d4b2e8a61c05
"""
from alembic import op
import sqlalchemy as sa

revision = "e5c3f9b72d16"
down_revision = "d4b2e8a61c05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("candidates", sa.Column("joining_letter_path", sa.String(500), nullable=True))
    op.add_column("candidates", sa.Column("joining_letter_filename", sa.String(255), nullable=True))
    op.add_column("candidates", sa.Column("salary_slip_path", sa.String(500), nullable=True))
    op.add_column("candidates", sa.Column("salary_slip_filename", sa.String(255), nullable=True))
    op.add_column("platform_settings", sa.Column("doc_require_offer_letter", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("platform_settings", sa.Column("doc_require_joining_letter", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("platform_settings", sa.Column("doc_require_salary_slip", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("platform_settings", sa.Column("doc_reminder_days", sa.Integer(), nullable=False, server_default="30"))


def downgrade():
    op.drop_column("platform_settings", "doc_reminder_days")
    op.drop_column("platform_settings", "doc_require_salary_slip")
    op.drop_column("platform_settings", "doc_require_joining_letter")
    op.drop_column("platform_settings", "doc_require_offer_letter")
    op.drop_column("candidates", "salary_slip_filename")
    op.drop_column("candidates", "salary_slip_path")
    op.drop_column("candidates", "joining_letter_filename")
    op.drop_column("candidates", "joining_letter_path")
