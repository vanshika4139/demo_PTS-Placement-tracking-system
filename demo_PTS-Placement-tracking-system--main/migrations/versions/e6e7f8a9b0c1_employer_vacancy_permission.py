"""employer_portal.vacancy permission for the Employer role

Revision ID: e6e7f8a9b0c1
Revises: e5d6e7f8a9b0
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "e6e7f8a9b0c1"
down_revision = "e5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not {"permissions", "roles", "role_permissions"}.issubset(set(inspect(bind).get_table_names())):
        return
    code, description = "employer_portal.vacancy", "Add and edit own vacancies in the employer portal"
    row = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).fetchone()
    if row:
        perm_id = row[0]
        bind.execute(sa.text("UPDATE permissions SET is_deleted = 0 WHERE id = :i"), {"i": perm_id})
    else:
        perm_id = uuid.uuid4().hex
        bind.execute(
            sa.text("INSERT INTO permissions (id, public_id, code, description, is_deleted) VALUES (:id, :pid, :code, :descr, 0)"),
            {"id": perm_id, "pid": str(uuid.uuid4()), "code": code, "descr": description},
        )
    role = bind.execute(sa.text("SELECT id FROM roles WHERE code = 'employer'")).fetchone()
    if not role:
        print("WARNING: employer role not found; permission created but not assigned.")
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