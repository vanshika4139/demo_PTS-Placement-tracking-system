"""revoked refresh tokens for rotation (Security 3.1)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "revoked_tokens",
        sa.Column("id", mysql.CHAR(32), primary_key=True),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("token_type", sa.String(16), nullable=False),
        sa.Column("user_id", mysql.CHAR(32), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"], unique=True)
    op.create_index("ix_revoked_tokens_user_id", "revoked_tokens", ["user_id"])


def downgrade():
    op.drop_index("ix_revoked_tokens_user_id", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_jti", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
