import uuid

from sqlalchemy import Boolean, Column, DateTime, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class UserPermissionOverride(db.Model):
    """A per-user exception to their role's permissions.

    is_allowed=True  -> this user CAN do this action, even if their role can't.
    is_allowed=False -> this user CANNOT do this action, even if their role can.

    Precedence: Super Admin bypass > this override > role permission > deny.
    """

    __tablename__ = "user_permission_overrides"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    user_id = Column(MySQLCHAR(32), nullable=False, index=True)
    permission_id = Column(MySQLCHAR(32), nullable=False, index=True)
    is_allowed = Column(Boolean, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)