"""add certificate fields to organizations and candidates

Revision ID: c3a1f9d27b10
Revises: fb08f0159c9c
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "c3a1f9d27b10"
down_revision = "fb08f0159c9c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("authority_name", sa.String(150), nullable=True))
    op.add_column("organizations", sa.Column("authority_designation", sa.String(150), nullable=True))
    op.add_column("organizations", sa.Column("signature_url", sa.String(500), nullable=True))
    op.add_column("candidates", sa.Column("certificate_file_path", sa.String(500), nullable=True))
    op.add_column("candidates", sa.Column("certificate_original_filename", sa.String(255), nullable=True))
    op.add_column("candidates", sa.Column("certificate_uploaded_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("candidates", "certificate_uploaded_at")
    op.drop_column("candidates", "certificate_original_filename")
    op.drop_column("candidates", "certificate_file_path")
    op.drop_column("organizations", "signature_url")
    op.drop_column("organizations", "authority_designation")
    op.drop_column("organizations", "authority_name")
