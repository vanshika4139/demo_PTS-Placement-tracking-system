"""add audit columns to activity_logs (FR-59)

Revision ID: f1a2b3c4d5e6
Revises: e8a9b0c1d2e3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "f1a2b3c4d5e6"
down_revision = "e8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activity_logs", sa.Column("module", sa.String(100), nullable=True))
    op.add_column("activity_logs", sa.Column("old_value", sa.Text(), nullable=True))
    op.add_column("activity_logs", sa.Column("new_value", sa.Text(), nullable=True))
    op.add_column("activity_logs", sa.Column("organization_id", mysql.CHAR(32), nullable=True))
    op.create_index("ix_activity_logs_organization_id", "activity_logs", ["organization_id"])
    # backfill organization for existing rows from the acting user
    op.execute(
        "UPDATE activity_logs a JOIN users u ON a.user_id = u.id "
        "SET a.organization_id = u.organization_id"
    )


def downgrade():
    op.drop_index("ix_activity_logs_organization_id", table_name="activity_logs")
    op.drop_column("activity_logs", "organization_id")
    op.drop_column("activity_logs", "new_value")
    op.drop_column("activity_logs", "old_value")
    op.drop_column("activity_logs", "module")
