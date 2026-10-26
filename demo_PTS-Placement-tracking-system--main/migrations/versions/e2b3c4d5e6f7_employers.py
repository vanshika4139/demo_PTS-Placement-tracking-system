"""employers table and employer permissions

Revision ID: e2b3c4d5e6f7
Revises: e1a2b3c4d5f6
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e2b3c4d5e6f7"
down_revision = "e1a2b3c4d5f6"
branch_labels = None
depends_on = None

ROLE_CODE = "organization_admin"
PERMISSIONS = [
    ("employer.view", "View employers"),
    ("employer.create", "Create employers"),
    ("employer.update", "Edit employers"),
    ("employer.delete", "Deactivate employers"),
]


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "employers" not in tables:
        op.create_table(
            "employers",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("employer_code", sa.String(20), nullable=False),
            sa.Column("company_name", sa.String(255), nullable=False),
            sa.Column("industry", sa.String(120), nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("contact_person", sa.String(150), nullable=True),
            sa.Column("mobile", sa.String(20), nullable=True),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("created_by", mysql.CHAR(32), nullable=True),
            sa.Column("modified_by", mysql.CHAR(32), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "employer_code", name="uq_employer_org_code"),
        )
        op.create_index("ix_employers_organization_id", "employers", ["organization_id"])

    if not {"permissions", "roles", "role_permissions"}.issubset(tables):
        return

    role = bind.execute(sa.text("SELECT id FROM roles WHERE code = :c"), {"c": ROLE_CODE}).fetchone()
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
        if not role:
            print("WARNING: role '%s' not found; permission %s created but not assigned." % (ROLE_CODE, code))
            continue
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