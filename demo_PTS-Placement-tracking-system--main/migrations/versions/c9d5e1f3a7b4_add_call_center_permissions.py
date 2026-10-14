"""add call center permissions (call_queue.view, call_log.create) and grant to Call Center Executive

Revision ID: c9d5e1f3a7b4
Revises: b8c4d0e2f6a3
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c9d5e1f3a7b4"
down_revision = "b8c4d0e2f6a3"
branch_labels = None
depends_on = None

# The Call Center Executive role has code "viewer" (display name renamed by rename_roles_srs.py).
ROLE_CODE = "viewer"
PERMISSIONS = [
    ("call_queue.view", "View own daily call queue"),
    ("call_log.create", "Log call disposition and notes"),
]


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"permissions", "roles", "role_permissions"}.issubset(tables):
        return

    # 1. Permissions
    perm_ids = {}
    for code, description in PERMISSIONS:
        row = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).fetchone()
        if row:
            perm_ids[code] = row[0]
            bind.execute(sa.text("UPDATE permissions SET is_deleted = 0 WHERE id = :i"), {"i": row[0]})
            continue
        new_id = uuid.uuid4().hex
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, public_id, code, description, is_deleted) "
                "VALUES (:id, :pid, :code, :descr, 0)"
            ),
            {"id": new_id, "pid": str(uuid.uuid4()), "code": code, "descr": description},
        )
        perm_ids[code] = new_id

    # 2. Grant to the Call Center Executive role (code "viewer")
    role = bind.execute(sa.text("SELECT id FROM roles WHERE code = :c"), {"c": ROLE_CODE}).fetchone()
    if not role:
        print("WARNING: role with code '%s' not found; call permissions created but not assigned." % ROLE_CODE)
        return

    for code, perm_id in perm_ids.items():
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
