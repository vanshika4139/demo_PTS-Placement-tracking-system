"""add voice and push to organization channel settings

Revision ID: fb08f0159c9c
Revises: 7763e5db9dff
Create Date: 2026-09-28 11:16:53

Only the 8 new Voice / Push columns (SRS FR-14). The unrelated index
drop/create operations that autogenerate picked up were removed on purpose.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fb08f0159c9c'
down_revision = '7763e5db9dff'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organization_channel_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('voice_provider', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('voice_api_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('voice_caller_id', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('voice_call_enabled', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('push_provider', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('push_server_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('push_sender_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('push_enabled', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization_channel_settings', schema=None) as batch_op:
        batch_op.drop_column('push_enabled')
        batch_op.drop_column('push_sender_id')
        batch_op.drop_column('push_server_key')
        batch_op.drop_column('push_provider')
        batch_op.drop_column('voice_call_enabled')
        batch_op.drop_column('voice_caller_id')
        batch_op.drop_column('voice_api_key')
        batch_op.drop_column('voice_provider')