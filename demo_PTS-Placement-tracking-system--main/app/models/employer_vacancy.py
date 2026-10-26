import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class EmployerVacancy(db.Model):
    """Open vacancy of an employer (Employer spec 3.2, FR-38). One employer can have many."""

    __tablename__ = "employer_vacancies"

    STATUSES = ("OPEN", "FILLED", "CLOSED")

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    employer_id = Column(MySQLCHAR(32), ForeignKey("employers.id"), nullable=False, index=True)
    job_title = Column(String(200), nullable=False)
    positions = Column(Integer, nullable=False, default=1)
    salary_min = Column(Numeric(12, 2), nullable=True)
    salary_max = Column(Numeric(12, 2), nullable=True)
    location = Column(String(255), nullable=True)
    vacancy_status = Column(String(20), nullable=False, default="OPEN")  # OPEN | FILLED | CLOSED
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active record, 0 = Inactive (never physically deleted)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)