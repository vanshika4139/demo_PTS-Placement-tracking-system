import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Employer(db.Model):
    """Employer / company record owned by one organization (Employer spec 3.1, FR-37)."""

    __tablename__ = "employers"
    __table_args__ = (UniqueConstraint("organization_id", "employer_code", name="uq_employer_org_code"),)

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    employer_code = Column(String(20), nullable=False)  # EMP00001
    company_name = Column(String(255), nullable=False)
    industry = Column(String(120), nullable=True)
    location = Column(String(255), nullable=True)
    contact_person = Column(String(150), nullable=True)
    mobile = Column(String(20), nullable=True)
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = Inactive (soft delete)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)