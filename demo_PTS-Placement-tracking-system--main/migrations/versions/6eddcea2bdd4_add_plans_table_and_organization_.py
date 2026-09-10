"""add plans table and organization billing fields

Revision ID: 6eddcea2bdd4
Revises: 230f52938eae
Create Date: 2026-09-10 16:02:07.580401

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '6eddcea2bdd4'
down_revision = '230f52938eae'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('billing_cycle', sa.String(length=20), nullable=True))
        batch_op.alter_column('subscription_plan_id',
               existing_type=mysql.BIGINT(),
               type_=mysql.CHAR(length=32),
               existing_nullable=True)
        batch_op.create_index(batch_op.f('ix_organizations_subscription_plan_id'), ['subscription_plan_id'], unique=False)
        batch_op.create_foreign_key(None, 'plans', ['subscription_plan_id'], ['id'])


def downgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_organizations_subscription_plan_id'))
        batch_op.alter_column('subscription_plan_id',
               existing_type=mysql.CHAR(length=32),
               type_=mysql.BIGINT(),
               existing_nullable=True)
        batch_op.drop_column('billing_cycle')

    op.drop_table('plans')