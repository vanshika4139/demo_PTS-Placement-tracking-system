"""add password reset token and expiry to candidates

Revision ID: 7d19ad5bd319
Revises: 42d7cf0834d1
Create Date: 2026-09-24 12:15:47.085189

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '7d19ad5bd319'
down_revision = '42d7cf0834d1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_reset_token', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('password_reset_expiry', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_column('password_reset_expiry')
        batch_op.drop_column('password_reset_token')