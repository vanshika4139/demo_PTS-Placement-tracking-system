"""add support_ticket.manage permission and grant it to Organization Admin

Revision ID: d2f8a4b6c0e7
Revises: d1e7f3a5b9c6
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "d2f8a4b6c0e7"
down_revision = "d1e7f3a5b9c6"
branch_labels = None
depends_on = None

ROLE_CODE = "organization_admin"
PERMISSION = ("support_ticket.manage", "Manage support tickets raised by own candidates")


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"permissions", "roles", "role_permissions"}.issubset(tables):
        return

    code, description = PERMISSION
    row = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).fetchone()
    if row:
        perm_id = row[0]
        bind.execute(sa.text("UPDATE permissions SET is_deleted = 0 WHERE id = :i"), {"i": perm_id})
    else:
        perm_id = uuid.uuid4().hex
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, public_id, code, description, is_deleted) "
                "VALUES (:id, :pid, :code, :descr, 0)"
            ),
            {"id": perm_id, "pid": str(uuid.uuid4()), "code": code, "descr": description},
        )

    role = bind.execute(sa.text("SELECT id FROM roles WHERE code = :c"), {"c": ROLE_CODE}).fetchone()
    if not role:
        print("WARNING: role with code '%s' not found; permission created but not assigned." % ROLE_CODE)
        return

    existing = bind.execute(
        sa.text("SELECT id FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
        {"r": role[0], "p": perm_id},
    ).fetchone()
    if existing:
        bind.execute(sa.text("UPDATE role_permissions SET is_deleted = 0 WHERE id = :i"), {"i": existing[0]})
    else:
        bind.execute(
            sa.text("INSERT INTO role_permissions (id, role_id, permission_id, is_deleted) VALUES (:id, :r, :p, 0)"),
            {"id": uuid.uuid4().hex, "r": role[0], "p": perm_id},
        )


def downgrade():
    pass