import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class UserSettings(db.Model):
    __tablename__ = "user_settings"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    user_id = Column(MySQLCHAR(32), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    email_notifications = Column(Boolean, nullable=False, default=True)
    sms_notifications = Column(Boolean, nullable=False, default=False)
    whatsapp_notifications = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)