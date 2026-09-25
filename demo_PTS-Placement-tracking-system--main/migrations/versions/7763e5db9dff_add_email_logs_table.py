"""add email_logs table

Revision ID: 7763e5db9dff
Revises: 7d19ad5bd319
Create Date: 2026-09-25 15:50:32.947391

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7763e5db9dff'
down_revision = '7d19ad5bd319'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('email_logs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('to_email', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.String(length=32), nullable=True),
        sa.Column('candidate_id', sa.String(length=32), nullable=True),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('has_attachment', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('email_logs')