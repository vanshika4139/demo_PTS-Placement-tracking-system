import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    user_id = Column(MySQLCHAR(32), ForeignKey("users.id"), nullable=True, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=True, index=True)
    organization_id = Column(String(50), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    type = Column(String(30), nullable=False, default="info")  # info, warning, success
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)