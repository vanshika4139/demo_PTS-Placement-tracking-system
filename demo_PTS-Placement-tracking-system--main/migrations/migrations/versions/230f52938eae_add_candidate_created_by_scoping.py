"""add candidate created_by scoping

Revision ID: 230f52938eae
Revises: 865e94383234
Create Date: 2026-09-10 00:00:00.000000

Adds a `created_by` column to `candidates` so records can be scoped to the
user who created them, and seeds a new `candidate.view_all` permission.

Behavior implemented in app code (see app/routes/frontend.py):
    - Super admins: always see all candidates (unchanged).
    - Users WITH `candidate.view_all` on their role: see all candidates in
      their organization (previous behavior for everyone).
    - Users WITHOUT `candidate.view_all`: only see candidates where
      created_by == their own user id.

`candidate.view_all` is NOT auto-assigned to any existing role here - do
that from the Roles & Permissions screen for whichever roles should keep
seeing every candidate in the org (e.g. Org Admin). Until you do that,
every non-super-admin user will only see candidates they personally
created, including on roles that previously saw everything.
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.sql import table, column

# revision identifiers, used by Alembic.
revision = '230f52938eae'
down_revision = '865e94383234'
branch_labels = None
depends_on = None

NEW_PERMISSION_CODE = "candidate.view_all"
NEW_PERMISSION_DESCRIPTION = "View all candidates in the organization, not just ones you created"


def upgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by', mysql.CHAR(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_candidates_created_by'), ['created_by'], unique=False)
        batch_op.create_foreign_key(
            batch_op.f('fk_candidates_created_by'), 'users', ['created_by'], ['id']
        )

    # Seed the new permission row. Existing roles are left untouched - a
    # super-admin must explicitly grant candidate.view_all to whichever
    # roles should keep seeing every candidate in the org.
    permissions_table = table(
        'permissions',
        column('id', mysql.CHAR(length=32)),
        column('public_id', sa.String(36)),
        column('code', sa.String(120)),
        column('description', sa.String(255)),
        column('is_deleted', sa.Boolean),
    )
    op.execute(
        permissions_table.insert().values(
            id=uuid.uuid4().hex,
            public_id=str(uuid.uuid4()),
            code=NEW_PERMISSION_CODE,
            description=NEW_PERMISSION_DESCRIPTION,
            is_deleted=False,
        )
    )


def downgrade():
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=NEW_PERMISSION_CODE)
    )

    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_candidates_created_by'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_candidates_created_by'))
        batch_op.drop_column('created_by')