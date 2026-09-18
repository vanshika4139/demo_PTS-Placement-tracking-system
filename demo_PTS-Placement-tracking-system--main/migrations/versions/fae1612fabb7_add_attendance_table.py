"""Add attendance table

Revision ID: fae1612fabb7
Revises: 02b4f09dc116
Create Date: 2026-09-18 07:52:42.126339

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'fae1612fabb7'
down_revision = '02b4f09dc116'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('attendance',
    sa.Column('id', mysql.CHAR(length=32), nullable=False),
    sa.Column('organization_id', sa.BigInteger(), nullable=False),
    sa.Column('candidate_id', mysql.CHAR(length=32), nullable=False),
    sa.Column('batch_id', mysql.CHAR(length=32), nullable=True),
    sa.Column('attendance_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('remarks', sa.String(length=255), nullable=True),
    sa.Column('marked_by', mysql.CHAR(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.ForeignKeyConstraint(['marked_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('candidate_id', 'attendance_date', name='uq_attendance_candidate_date')
    )
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attendance_attendance_date'), ['attendance_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendance_batch_id'), ['batch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendance_candidate_id'), ['candidate_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendance_organization_id'), ['organization_id'], unique=False)


def downgrade():
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attendance_organization_id'))
        batch_op.drop_index(batch_op.f('ix_attendance_candidate_id'))
        batch_op.drop_index(batch_op.f('ix_attendance_batch_id'))
        batch_op.drop_index(batch_op.f('ix_attendance_attendance_date'))

    op.drop_table('attendance')