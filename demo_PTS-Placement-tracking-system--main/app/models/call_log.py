import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CallLog(db.Model):
    """One row per call: notes, duration, disposition, recording pointer
    (spec 3.2 / 3.3, FR-34 / FR-35)."""

    __tablename__ = "call_logs"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    call_task_id = Column(MySQLCHAR(32), ForeignKey("call_tasks.id"), nullable=True, index=True)
    disposition_id = Column(MySQLCHAR(32), ForeignKey("call_dispositions.id"), nullable=True, index=True)
    call_notes = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    # Recording is ON HOLD (provider / storage / retention unconfirmed).
    # Only a path + metadata is ever stored, never the file itself.
    recording_path = Column(String(500), nullable=True)
    recording_metadata = Column(Text, nullable=True)
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = soft-deleted
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
