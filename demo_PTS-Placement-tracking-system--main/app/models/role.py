import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Role(db.Model):
    __tablename__ = "roles"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    public_id = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    code = Column(String(120), unique=True, nullable=False)
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)