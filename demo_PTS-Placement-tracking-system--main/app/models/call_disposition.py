import uuid

from sqlalchemy import Column, DateTime, Integer, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CallDisposition(db.Model):
    """Master data maintained by Super Admin (Call Center spec 3.3).
    Platform-wide, not scoped to an organization."""

    __tablename__ = "call_dispositions"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    code = Column(String(50), unique=True, nullable=False)  # CONNECTED, PLACED, LEFT_JOB ...
    name = Column(String(80), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = soft-deleted
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
