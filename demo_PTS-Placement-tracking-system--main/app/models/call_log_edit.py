import uuid

from sqlalchemy import BigInteger, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CallLogEdit(db.Model):
    """One row per edit of a logged call: old value, new value, who, when."""

    __tablename__ = "call_log_edits"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, nullable=False, index=True)
    call_log_id = Column(MySQLCHAR(32), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), nullable=True)
    old_disposition_id = Column(MySQLCHAR(32), nullable=True)
    new_disposition_id = Column(MySQLCHAR(32), nullable=True)
    old_notes = Column(Text, nullable=True)
    new_notes = Column(Text, nullable=True)
    old_duration_seconds = Column(Integer, nullable=True)
    new_duration_seconds = Column(Integer, nullable=True)
    edited_by = Column(MySQLCHAR(32), nullable=True)
    edited_at = Column(DateTime, server_default=func.now(), nullable=False)