import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CandidatePlacement(db.Model):
    """One placement of one candidate at one employer (Employer spec 3.3, FR-39).
    History is never overwritten: leaving an employer sets LEFT, joining another creates a new row."""

    __tablename__ = "candidate_placements"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    employer_id = Column(MySQLCHAR(32), ForeignKey("employers.id"), nullable=False, index=True)
    job_role = Column(String(255), nullable=True)
    salary = Column(String(40), nullable=True)
    location = Column(String(255), nullable=True)
    joining_date = Column(DateTime, nullable=True)
    working_status = Column(String(20), nullable=False, default="WORKING")  # WORKING | LEFT
    exit_date = Column(DateTime, nullable=True)
    exit_reason = Column(String(255), nullable=True)
    status = Column(SmallInteger, nullable=False, default=1)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)