import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CallTask(db.Model):
    """One call assigned to a Call Center Executive (spec 3.1, FR-33)."""

    __tablename__ = "call_tasks"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    assigned_user_id = Column(MySQLCHAR(32), ForeignKey("users.id"), nullable=False, index=True)
    follow_up_checkpoint_id = Column(MySQLCHAR(32), ForeignKey("follow_up_checkpoints.id"), nullable=True)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    task_status = Column(String(20), nullable=False, default="pending")  # pending | completed | missed
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = soft-deleted
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
