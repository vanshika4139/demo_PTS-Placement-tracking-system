"""convert organization district_id to district text field

Revision ID: 9f3c1a7d5e21
Revises: 6eddcea2bdd4
Create Date: 2026-09-11 00:00:00.000000

Organizations never had a districts master table, so `district_id` was
always just a raw number with nothing to look it up against. This
migration replaces it with a free-text `district` column so admins can
actually type a district name in the Organization form.

Data preservation: any existing `district_id` value is copied into the
new `district` column as a string (e.g. 4 -> "4") before the old column
is dropped, so nothing is silently lost. Since those numbers were never
resolvable to a real district name in the first place, you'll likely
want to manually edit affected organizations afterwards to put in the
actual district name.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '9f3c1a7d5e21'
down_revision = '6eddcea2bdd4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('district', sa.String(length=150), nullable=True))

    # Copy old numeric district_id values across as text before dropping the column.
    op.execute(
        "UPDATE organizations SET district = CAST(district_id AS CHAR) WHERE district_id IS NOT NULL"
    )

    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('district_id')


def downgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('district_id', mysql.BIGINT(), nullable=True))

    # Only numeric-looking district values can be restored to district_id;
    # anything an admin typed as a real district name (non-numeric) is lost
    # on downgrade - this is expected, since the whole point of this
    # migration was to move away from meaningless numeric IDs.
    op.execute(
        "UPDATE organizations SET district_id = CAST(district AS UNSIGNED) "
        "WHERE district IS NOT NULL AND district REGEXP '^[0-9]+$'"
    )

    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('district')