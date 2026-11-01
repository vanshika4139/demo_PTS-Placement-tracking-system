"""encrypt salary columns (Security 3.4)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("candidates", "candidate_placements"):
        op.alter_column(table, "salary", existing_type=sa.String(40), type_=sa.String(500), existing_nullable=True)


def downgrade():
    # encrypted values will not fit in 40 characters; decrypt first before downgrading
    for table in ("candidates", "candidate_placements"):
        op.alter_column(table, "salary", existing_type=sa.String(500), type_=sa.String(40), existing_nullable=True)
