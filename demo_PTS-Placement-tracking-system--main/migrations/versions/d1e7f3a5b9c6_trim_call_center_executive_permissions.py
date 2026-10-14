"""trim Call Center Executive (role code 'viewer') to queue + call logging only

Revision ID: d1e7f3a5b9c6
Revises: c9d5e1f3a7b4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "d1e7f3a5b9c6"
down_revision = "c9d5e1f3a7b4"
branch_labels = None
depends_on = None

ROLE_CODE = "viewer"
REVOKE = [
    "candidate.view",
    "batch.view",
    "scheme.view",
    "placement.view",
    "tracking.view",
    "report.view",
]


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"permissions", "roles", "role_permissions"}.issubset(tables):
        return
    role = bind.execute(sa.text("SELECT id FROM roles WHERE code = :c"), {"c": ROLE_CODE}).fetchone()
    if not role:
        print("WARNING: role with code '%s' not found; nothing revoked." % ROLE_CODE)
        return
    for code in REVOKE:
        bind.execute(
            sa.text(
                "UPDATE role_permissions SET is_deleted = 1 WHERE role_id = :r AND permission_id IN "
                "(SELECT id FROM permissions WHERE code = :code)"
            ),
            {"r": role[0], "code": code},
        )


def downgrade():
    pass