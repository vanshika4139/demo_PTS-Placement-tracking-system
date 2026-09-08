import uuid

from sqlalchemy import Column, DateTime, Integer, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class SubModule(db.Model):
    """A menu item under a Module, e.g. 'Candidate List' under 'Candidate Management'.

    permission_key is the stable identifier (e.g. 'candidate.view') used to check
    access both in the menu and in backend route authorization.
    """

    __tablename__ = "sub_module"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    module_id = Column(MySQLCHAR(32), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    sub_url = Column(String(255), nullable=False)
    permission_key = Column(String(100), nullable=False, unique=True, index=True)
    sub_module_order_no = Column(Integer, nullable=False, default=0)
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = Inactive
    created_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    modified_at = Column(DateTime, onupdate=func.now(), nullable=True)