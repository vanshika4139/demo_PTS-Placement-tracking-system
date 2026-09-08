import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    user_id = Column(MySQLCHAR(32), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    details = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)