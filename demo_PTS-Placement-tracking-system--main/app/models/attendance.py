import uuid

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Attendance(db.Model):
    """SRS Platform-Wide Reporting (FR-17): per-candidate, per-day attendance
    record so the Reports page can segment by attendance the same way it
    already does for placement/verification status.

    One row per (candidate, date) - the unique constraint below prevents a
    trainer from accidentally marking the same candidate twice for the same
    day. Re-marking a day is an update to the existing row, not a new insert
    (see the route: it upserts rather than always inserting)."""

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("candidate_id", "attendance_date", name="uq_attendance_candidate_date"),
    )

    STATUSES = ("present", "absent", "leave")

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    batch_id = Column(MySQLCHAR(32), ForeignKey("batches.id"), nullable=True, index=True)
    attendance_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="present")
    remarks = Column(String(255), nullable=True)
    marked_by = Column(MySQLCHAR(32), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)