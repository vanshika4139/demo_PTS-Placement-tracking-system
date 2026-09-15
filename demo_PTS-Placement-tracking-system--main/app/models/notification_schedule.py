import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class NotificationSchedule(db.Model):
    """When a MessageTemplate should be sent (SRS FR-16). One template can
    have multiple schedules (e.g. a reminder sent both weekly and on a
    custom date). day_of_week/day_of_month/custom_cron_expression are only
    read for the matching frequency - e.g. day_of_month is ignored unless
    frequency == "monthly".

    last_run_at is set by the scheduler job after a successful run, so it
    does not fire twice for the same period.
    """

    __tablename__ = "notification_schedules"

    FREQUENCIES = ("daily", "weekly", "monthly", "custom")

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    template_id = Column(MySQLCHAR(32), ForeignKey("message_templates.id"), nullable=False, index=True)
    frequency = Column(String(20), nullable=False)
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    custom_cron_expression = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    template = relationship("MessageTemplate")
