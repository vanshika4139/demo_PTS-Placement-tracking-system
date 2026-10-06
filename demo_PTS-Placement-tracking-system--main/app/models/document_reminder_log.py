import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class DocumentReminderLog(db.Model):
    """Records which post-placement document reminder (day 7/15/30) was
    already emailed to a candidate, so each one is sent only once."""
    __tablename__ = "document_reminder_logs"
    __table_args__ = (
        UniqueConstraint("candidate_id", "reminder_day", name="uq_doc_reminder_candidate_day"),
    )

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    reminder_day = Column(Integer, nullable=False)
    sent_at = Column(DateTime, server_default=func.now(), nullable=False)
