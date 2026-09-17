"""add user_sessions table

Revision ID: 02b4f09dc116
Revises: 4b8e6c2a91f3
Create Date: 2026-09-17 08:39:41.628557

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '02b4f09dc116'
down_revision = '4b8e6c2a91f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user_sessions',
    sa.Column('id', mysql.CHAR(length=32), nullable=False),
    sa.Column('session_token', mysql.CHAR(length=32), nullable=False),
    sa.Column('user_id', mysql.CHAR(length=32), nullable=False),
    sa.Column('user_email', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_active_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_session_token'), ['session_token'], unique=True)
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_sessions_session_token'))

    op.drop_table('user_sessions')
