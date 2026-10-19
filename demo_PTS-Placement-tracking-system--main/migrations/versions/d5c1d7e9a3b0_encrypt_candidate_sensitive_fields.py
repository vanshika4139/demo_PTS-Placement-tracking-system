"""encrypt candidate Aadhaar, PAN and bank details; add aadhaar_hash

Revision ID: d5c1d7e9a3b0
Revises: d4b0c6d8f2a9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "d5c1d7e9a3b0"
down_revision = "d4b0c6d8f2a9"
branch_labels = None
depends_on = None

ENC_COLS = ["aadhaar", "pan", "account_number", "ifsc", "upi_id"]


def upgrade():
    from app.utils.crypto import PREFIX, aadhaar_hash, encrypt_value

    bind = op.get_bind()
    insp = inspect(bind)
    if "candidates" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("candidates")}

    # Fails early with a clear message if ENCRYPTION_KEY is missing.
    encrypt_value("key check")

    for col in ENC_COLS:
        if col in cols:
            op.alter_column("candidates", col, existing_type=sa.String(120), type_=sa.String(500), existing_nullable=True)

    if "aadhaar_hash" not in cols:
        op.add_column("candidates", sa.Column("aadhaar_hash", sa.String(64), nullable=True))
        op.create_index("ix_candidates_aadhaar_hash", "candidates", ["aadhaar_hash"])

    rows = bind.execute(sa.text("SELECT id, aadhaar, pan, account_number, ifsc, upi_id FROM candidates")).fetchall()
    for row in rows:
        values = {}
        for i, col in enumerate(ENC_COLS, start=1):
            v = row[i]
            if v and not str(v).startswith(PREFIX):
                values[col] = encrypt_value(v)
        if row[1] and not str(row[1]).startswith(PREFIX):
            values["aadhaar_hash"] = aadhaar_hash(row[1])
        if values:
            sets = ", ".join(f"{k} = :{k}" for k in values)
            bind.execute(sa.text(f"UPDATE candidates SET {sets} WHERE id = :cid"), {**values, "cid": row[0]})


def downgrade():
    pass