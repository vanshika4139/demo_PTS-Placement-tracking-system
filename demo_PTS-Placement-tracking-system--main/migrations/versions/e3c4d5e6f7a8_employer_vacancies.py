"""employer_vacancies table and vacancy permissions

Revision ID: e3c4d5e6f7a8
Revises: e2b3c4d5e6f7
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e3c4d5e6f7a8"
down_revision = "e2b3c4d5e6f7"
branch_labels = None
depends_on = None

ROLE_CODE = "organization_admin"
PERMISSIONS = [
    ("vacancy.view", "View employer vacancies"),
    ("vacancy.create", "Create employer vacancies"),
    ("vacancy.update", "Edit employer vacancies"),
]


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "employer_vacancies" not in tables:
        op.create_table(
            "employer_vacancies",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("employer_id", mysql.CHAR(32), sa.ForeignKey("employers.id"), nullable=False),
            sa.Column("job_title", sa.String(200), nullable=False),
            sa.Column("positions", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("salary_min", sa.Numeric(12, 2), nullable=True),
            sa.Column("salary_max", sa.Numeric(12, 2), nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("vacancy_status", sa.String(20), nullable=False, server_default="OPEN"),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("created_by", mysql.CHAR(32), nullable=True),
            sa.Column("modified_by", mysql.CHAR(32), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_employer_vacancies_organization_id", "employer_vacancies", ["organization_id"])
        op.create_index("ix_employer_vacancies_employer_id", "employer_vacancies", ["employer_id"])

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