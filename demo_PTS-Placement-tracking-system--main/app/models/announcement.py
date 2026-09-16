import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Announcement(db.Model):
    """A platform-wide broadcast message shown as a banner to every
    logged-in user (organization admins, candidates, everyone) until
    deactivated by a super admin. Not tied to any one organization -
    unlike Notification, which is scoped per-user/org/candidate."""

    __tablename__ = "announcements"

    TYPES = ("info", "warning", "success")

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(20), nullable=False, default="info")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
