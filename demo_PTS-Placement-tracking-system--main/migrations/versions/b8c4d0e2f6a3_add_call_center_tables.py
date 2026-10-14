"""add call center tables (call_dispositions, call_tasks, call_logs) and seed dispositions

Revision ID: b8c4d0e2f6a3
Revises: a7b3c9d1e5f2
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "b8c4d0e2f6a3"
down_revision = "a7b3c9d1e5f2"
branch_labels = None
depends_on = None

DISPOSITIONS = [
    ("CONNECTED", "Connected"),
    ("BUSY", "Busy"),
    ("WRONG_NUMBER", "Wrong Number"),
    ("SWITCHED_OFF", "Switched Off"),
    ("FOLLOW_UP_REQUIRED", "Follow-up Required"),
    ("PLACED", "Placed"),
    ("LEFT_JOB", "Left Job"),
]


def _char32():
    return mysql.CHAR(length=32)


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "call_dispositions" not in tables:
        op.create_table(
            "call_dispositions",
            sa.Column("id", _char32(), primary_key=True),
            sa.Column("code", sa.String(50), nullable=False, unique=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("created_by", _char32(), nullable=True),
            sa.Column("modified_by", _char32(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if "call_tasks" not in tables:
        op.create_table(
            "call_tasks",
            sa.Column("id", _char32(), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("candidate_id", _char32(), sa.ForeignKey("candidates.id"), nullable=False),
            sa.Column("assigned_user_id", _char32(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("follow_up_checkpoint_id", _char32(), sa.ForeignKey("follow_up_checkpoints.id"), nullable=True),
            sa.Column("scheduled_at", sa.DateTime(), nullable=False),
            sa.Column("task_status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("created_by", _char32(), nullable=True),
            sa.Column("modified_by", _char32(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_call_tasks_organization_id", "call_tasks", ["organization_id"])
        op.create_index("ix_call_tasks_candidate_id", "call_tasks", ["candidate_id"])
        op.create_index("ix_call_tasks_assigned_user_id", "call_tasks", ["assigned_user_id"])
        op.create_index("ix_call_tasks_scheduled_at", "call_tasks", ["scheduled_at"])

    if "call_logs" not in tables:
        op.create_table(
            "call_logs",
            sa.Column("id", _char32(), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("candidate_id", _char32(), sa.ForeignKey("candidates.id"), nullable=False),
            sa.Column("call_task_id", _char32(), sa.ForeignKey("call_tasks.id"), nullable=True),
            sa.Column("disposition_id", _char32(), sa.ForeignKey("call_dispositions.id"), nullable=True),
            sa.Column("call_notes", sa.Text(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("recording_path", sa.String(500), nullable=True),
            sa.Column("recording_metadata", sa.Text(), nullable=True),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("created_by", _char32(), nullable=True),
            sa.Column("modified_by", _char32(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_call_logs_organization_id", "call_logs", ["organization_id"])
        op.create_index("ix_call_logs_candidate_id", "call_logs", ["candidate_id"])
        op.create_index("ix_call_logs_call_task_id", "call_logs", ["call_task_id"])
        op.create_index("ix_call_logs_disposition_id", "call_logs", ["disposition_id"])

    existing = {r[0] for r in bind.execute(sa.text("SELECT code FROM call_dispositions"))}
    for order, (code, name) in enumerate(DISPOSITIONS, start=1):
        if code not in existing:
            bind.execute(
                sa.text(
                    "INSERT INTO call_dispositions (id, code, name, display_order, status) "
                    "VALUES (:id, :code, :name, :ord, 1)"
                ),
                {"id": uuid.uuid4().hex, "code": code, "name": name, "ord": order},
            )


def downgrade():
    pass
