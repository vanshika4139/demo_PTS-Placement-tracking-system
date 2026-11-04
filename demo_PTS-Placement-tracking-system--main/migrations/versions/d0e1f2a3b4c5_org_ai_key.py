"""org own AI key columns + plan allow_own_ai_key (AI-Powered Features)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("ai_provider", sa.String(30), nullable=True))
    # holds the Fernet-encrypted key, so Text (ciphertext is longer than the key)
    op.add_column("organizations", sa.Column("ai_api_key", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("ai_model", sa.String(100), nullable=True))
    op.add_column("plans", sa.Column("allow_own_ai_key", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("plans", "allow_own_ai_key")
    op.drop_column("organizations", "ai_model")
    op.drop_column("organizations", "ai_api_key")
    op.drop_column("organizations", "ai_provider")