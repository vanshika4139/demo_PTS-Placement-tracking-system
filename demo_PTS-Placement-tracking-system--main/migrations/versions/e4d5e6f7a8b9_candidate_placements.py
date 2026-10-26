"""candidate_placements and verifications tables, with backfill of existing placed candidates

Revision ID: e4d5e6f7a8b9
Revises: e3c4d5e6f7a8
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

revision = "e4d5e6f7a8b9"
down_revision = "e3c4d5e6f7a8"
branch_labels = None
depends_on = None


def _next_code(highest_by_org, org_id):
    highest_by_org[org_id] = highest_by_org.get(org_id, 0) + 1
    return "EMP%05d" % highest_by_org[org_id]


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "candidate_placements" not in tables:
        op.create_table(
            "candidate_placements",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("candidate_id", mysql.CHAR(32), sa.ForeignKey("candidates.id"), nullable=False),
            sa.Column("employer_id", mysql.CHAR(32), sa.ForeignKey("employers.id"), nullable=False),
            sa.Column("job_role", sa.String(255), nullable=True),
            sa.Column("salary", sa.String(40), nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("joining_date", sa.DateTime(), nullable=True),
            sa.Column("working_status", sa.String(20), nullable=False, server_default="WORKING"),
            sa.Column("exit_date", sa.DateTime(), nullable=True),
            sa.Column("exit_reason", sa.String(255), nullable=True),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("created_by", mysql.CHAR(32), nullable=True),
            sa.Column("modified_by", mysql.CHAR(32), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_candidate_placements_organization_id", "candidate_placements", ["organization_id"])
        op.create_index("ix_candidate_placements_candidate_id", "candidate_placements", ["candidate_id"])
        op.create_index("ix_candidate_placements_employer_id", "candidate_placements", ["employer_id"])

    if "verifications" not in tables:
        op.create_table(
            "verifications",
            sa.Column("id", mysql.CHAR(32), primary_key=True),
            sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("candidate_id", mysql.CHAR(32), sa.ForeignKey("candidates.id"), nullable=False),
            sa.Column("placement_id", mysql.CHAR(32), sa.ForeignKey("candidate_placements.id"), nullable=False),
            sa.Column("employer_id", mysql.CHAR(32), sa.ForeignKey("employers.id"), nullable=False),
            sa.Column("verification_type", sa.String(30), nullable=False, server_default="EMPLOYER"),
            sa.Column("verification_status", sa.String(30), nullable=False, server_default="pending"),
            sa.Column("verified_by", mysql.CHAR(32), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_verifications_organization_id", "verifications", ["organization_id"])
        op.create_index("ix_verifications_candidate_id", "verifications", ["candidate_id"])
        op.create_index("ix_verifications_placement_id", "verifications", ["placement_id"])
        op.create_index("ix_verifications_employer_id", "verifications", ["employer_id"])

    # Backfill: existing placed candidates get an employer, a placement and a verification row.
    highest = {}
    for org_id, code in bind.execute(sa.text("SELECT organization_id, employer_code FROM employers")).fetchall():
        digits = "".join(ch for ch in (code or "") if ch.isdigit())
        if digits:
            highest[org_id] = max(highest.get(org_id, 0), int(digits))

    employer_cache = {}
    made_employers = made_placements = 0
    rows = bind.execute(sa.text(
        "SELECT id, organization_id, employer_name, job_role, salary, location, joining_date, working_status, "
        "exit_date, exit_reason, verification_status FROM candidates "
        "WHERE is_deleted = 0 AND employer_name IS NOT NULL AND TRIM(employer_name) <> ''"
    )).fetchall()

    for (cid, org_id, ename, role, salary, location, joining, wstatus, exit_date, exit_reason, vstatus) in rows:
        if bind.execute(sa.text("SELECT id FROM candidate_placements WHERE candidate_id = :c LIMIT 1"), {"c": cid}).fetchone():
            continue
        name = ename.strip()
        key = (org_id, name.lower())
        employer_id = employer_cache.get(key)
        if not employer_id:
            found = bind.execute(
                sa.text("SELECT id FROM employers WHERE organization_id = :o AND LOWER(company_name) = :n AND status = 1 LIMIT 1"),
                {"o": org_id, "n": name.lower()},
            ).fetchone()
            if found:
                employer_id = found[0]
            else:
                employer_id = uuid.uuid4().hex
                bind.execute(
                    sa.text("INSERT INTO employers (id, organization_id, employer_code, company_name, status) VALUES (:id, :o, :code, :name, 1)"),
                    {"id": employer_id, "o": org_id, "code": _next_code(highest, org_id), "name": name[:255]},
                )
                made_employers += 1
            employer_cache[key] = employer_id

        left = exit_date is not None or (wstatus or "").strip().lower() == "left"
        placement_id = uuid.uuid4().hex
        bind.execute(
            sa.text(
                "INSERT INTO candidate_placements (id, organization_id, candidate_id, employer_id, job_role, salary, location, "
                "joining_date, working_status, exit_date, exit_reason, status) "
                "VALUES (:id, :o, :c, :e, :role, :sal, :loc, :jd, :ws, :ed, :er, 1)"
            ),
            {"id": placement_id, "o": org_id, "c": cid, "e": employer_id, "role": role, "sal": salary, "loc": location,
             "jd": joining, "ws": "LEFT" if left else "WORKING", "ed": exit_date, "er": exit_reason},
        )
        bind.execute(
            sa.text(
                "INSERT INTO verifications (id, organization_id, candidate_id, placement_id, employer_id, verification_type, verification_status) "
                "VALUES (:id, :o, :c, :p, :e, 'EMPLOYER', :vs)"
            ),
            {"id": uuid.uuid4().hex, "o": org_id, "c": cid, "p": placement_id, "e": employer_id, "vs": (vstatus or "pending")},
        )
        made_placements += 1
    print("Backfill: %d employers and %d placements created." % (made_employers, made_placements))


def downgrade():
    pass