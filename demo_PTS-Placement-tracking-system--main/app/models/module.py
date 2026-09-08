import uuid

from sqlalchemy import Column, DateTime, Integer, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Module(db.Model):
    """A top-level left-menu item, e.g. Dashboard, Candidate Management, Reports."""

    __tablename__ = "module"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    name = Column(String(150), nullable=False)
    order_no = Column(Integer, nullable=False, default=0)
    icon_image = Column(String(255), nullable=True)
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = Inactive
    created_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    modified_at = Column(DateTime, onupdate=func.now(), nullable=True)