"""candidate_evidence table

Revision ID: e7f8a9b0c1d2
Revises: e6e7f8a9b0c1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e7f8a9b0c1d2"
down_revision = "e6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "candidate_evidence" in set(inspect(bind).get_table_names()):
        return
    op.create_table(
        "candidate_evidence",
        sa.Column("id", mysql.CHAR(32), primary_key=True),
        sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("candidate_id", mysql.CHAR(32), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("placement_id", mysql.CHAR(32), nullable=True),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("latitude", sa.String(20), nullable=True),
        sa.Column("longitude", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "evidence_type", name="uq_candidate_evidence_type"),
    )
    op.create_index("ix_candidate_evidence_organization_id", "candidate_evidence", ["organization_id"])
    op.create_index("ix_candidate_evidence_candidate_id", "candidate_evidence", ["candidate_id"])
    op.create_index("ix_candidate_evidence_placement_id", "candidate_evidence", ["placement_id"])


def downgrade():
    pass