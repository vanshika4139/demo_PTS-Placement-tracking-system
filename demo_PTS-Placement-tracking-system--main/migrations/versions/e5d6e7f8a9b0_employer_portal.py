"""users.employer_id, Employer role and employer portal permissions

Revision ID: e5d6e7f8a9b0
Revises: e4d5e6f7a8b9
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e5d6e7f8a9b0"
down_revision = "e4d5e6f7a8b9"
branch_labels = None
depends_on = None

ROLE_CODE = "employer"
PERMISSIONS = [
    ("employer_portal.view", "View the employer dashboard and own placements"),
    ("employer_portal.verify", "Verify or reject own candidates' placements"),
]


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "employer_id" not in {c["name"] for c in insp.get_columns("users")}:
        op.add_column("users", sa.Column("employer_id", mysql.CHAR(32), nullable=True))
        op.create_index("ix_users_employer_id", "users", ["employer_id"])

    tables = set(insp.get_table_names())
    if not {"permissions", "roles", "role_permissions"}.issubset(tables):
        return

    role = bind.execute(sa.text("SELECT id FROM roles WHERE code = :c"), {"c": ROLE_CODE}).fetchone()
    if role:
        role_id = role[0]
        bind.execute(sa.text("UPDATE roles SET is_deleted = 0 WHERE id = :i"), {"i": role_id})
    else:
        role_id = uuid.uuid4().hex
        bind.execute(
            sa.text("INSERT INTO roles (id, public_id, name, code, organization_id, is_deleted) VALUES (:id, :pid, 'Employer', :code, NULL, 0)"),
            {"id": role_id, "pid": str(uuid.uuid4()), "code": ROLE_CODE},
        )

    for code, description in PERMISSIONS:
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
        existing = bind.execute(
            sa.text("SELECT id FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
            {"r": role_id, "p": perm_id},
        ).fetchone()
        if existing:
            bind.execute(sa.text("UPDATE role_permissions SET is_deleted = 0 WHERE id = :i"), {"i": existing[0]})
        else:
            bind.execute(
                sa.text("INSERT INTO role_permissions (id, role_id, permission_id, is_deleted) VALUES (:id, :r, :p, 0)"),
                {"id": uuid.uuid4().hex, "r": role_id, "p": perm_id},
            )


def downgrade():
    pass