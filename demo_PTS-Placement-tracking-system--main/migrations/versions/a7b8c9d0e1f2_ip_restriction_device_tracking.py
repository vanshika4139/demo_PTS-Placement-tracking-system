"""admin IP restriction and device tracking (FR-60)

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("allowed_ips", sa.Text(), nullable=True))
    op.add_column("login_history", sa.Column("device_hash", sa.String(64), nullable=True))
    op.create_index("ix_login_history_device_hash", "login_history", ["device_hash"])
    op.execute(
        "UPDATE login_history SET device_hash = LEFT(SHA2(COALESCE(LEFT(user_agent, 500), ''), 256), 32) "
        "WHERE device_hash IS NULL"
    )


def downgrade():
    op.drop_index("ix_login_history_device_hash", table_name="login_history")
    op.drop_column("login_history", "device_hash")
    op.drop_column("users", "allowed_ips")
