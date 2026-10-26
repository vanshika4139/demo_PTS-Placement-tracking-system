import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Verification(db.Model):
    """Verification of one placement. Kept in its own field, not in the candidate's common status."""

    __tablename__ = "verifications"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    placement_id = Column(MySQLCHAR(32), ForeignKey("candidate_placements.id"), nullable=False, index=True)
    employer_id = Column(MySQLCHAR(32), ForeignKey("employers.id"), nullable=False, index=True)
    verification_type = Column(String(30), nullable=False, default="EMPLOYER")
    verification_status = Column(String(30), nullable=False, default="pending")  # pending | verified
    verified_by = Column(MySQLCHAR(32), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)