import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class UserRole(db.Model):
    __tablename__ = "user_roles"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    user_id = Column(MySQLCHAR(32), ForeignKey("users.id"), nullable=False)
    role_id = Column(MySQLCHAR(32), ForeignKey("roles.id"), nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
