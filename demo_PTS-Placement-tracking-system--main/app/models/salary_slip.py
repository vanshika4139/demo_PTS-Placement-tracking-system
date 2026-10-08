import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR
from sqlalchemy.orm import relationship, backref

from app.extensions import db


class SalarySlip(db.Model):
    """One uploaded salary slip per candidate per month (month = 'YYYY-MM')."""
    __tablename__ = "salary_slips"
    __table_args__ = (
        UniqueConstraint("candidate_id", "month", name="uq_salary_slip_candidate_month"),
    )

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    month = Column(String(7), nullable=False)
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)

    candidate = relationship(
        "Candidate",
        backref=backref("salary_slips", order_by="SalarySlip.month.desc()", lazy="select"),
    )
