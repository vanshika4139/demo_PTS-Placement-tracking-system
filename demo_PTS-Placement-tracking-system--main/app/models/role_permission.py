import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class RolePermission(db.Model):
    __tablename__ = "role_permissions"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    role_id = Column(MySQLCHAR(32), ForeignKey("roles.id"), nullable=False)
    permission_id = Column(MySQLCHAR(32), ForeignKey("permissions.id"), nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)