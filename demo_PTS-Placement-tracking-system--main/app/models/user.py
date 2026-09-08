import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    public_id = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    username = Column(String(100), unique=True, nullable=True)
    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=True)
    is_super_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)