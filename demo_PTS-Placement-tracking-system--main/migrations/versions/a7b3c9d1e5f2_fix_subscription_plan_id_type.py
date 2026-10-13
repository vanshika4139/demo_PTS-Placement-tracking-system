"""fix organizations.subscription_plan_id type (bigint -> char(32))

Revision ID: a7b3c9d1e5f2
Revises: f6d4a0c83e27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "a7b3c9d1e5f2"
down_revision = "f6d4a0c83e27"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    col = next((c for c in insp.get_columns("organizations") if c["name"] == "subscription_plan_id"), None)
    if col is None:
        return

    # 1. Column type: only change if it is not already CHAR(32)
    is_char = isinstance(col["type"], (sa.CHAR, sa.String)) and getattr(col["type"], "length", None) == 32
    if not is_char:
        # junk 0 values (old bigint default) match no plan
        op.execute("UPDATE organizations SET subscription_plan_id = NULL")
        op.execute("ALTER TABLE organizations MODIFY subscription_plan_id CHAR(32) NULL")

    # 2. Index
    insp = inspect(bind)
    has_index = any("subscription_plan_id" in (i.get("column_names") or []) for i in insp.get_indexes("organizations"))
    if not has_index:
        op.create_index("ix_organizations_subscription_plan_id", "organizations", ["subscription_plan_id"], unique=False)

    # 3. Foreign key to plans.id
    has_fk = any(
        fk.get("referred_table") == "plans" and "subscription_plan_id" in fk.get("constrained_columns", [])
        for fk in insp.get_foreign_keys("organizations")
    )
    if not has_fk:
        op.create_foreign_key("fk_organizations_subscription_plan_id", "organizations", "plans", ["subscription_plan_id"], ["id"])


def downgrade():
    pass
