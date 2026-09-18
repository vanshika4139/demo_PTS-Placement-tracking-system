"""Add ai_call_allowance to plans and organizations

Revision ID: 42d7cf0834d1
Revises: 8687e6b66f60
Create Date: 2026-09-18 14:11:26.704217

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '42d7cf0834d1'
down_revision = '8687e6b66f60'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_call_allowance', sa.Integer(), nullable=True))

    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_call_allowance', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_column('ai_call_allowance')

    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('ai_call_allowance')