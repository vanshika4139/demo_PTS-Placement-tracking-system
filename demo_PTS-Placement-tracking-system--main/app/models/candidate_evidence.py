import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CandidateEvidence(db.Model):
    """Placement evidence uploaded by the candidate (Org Admin spec FR-30):
    location, photo, experience letter, bank statement. One row per candidate per type."""

    __tablename__ = "candidate_evidence"
    __table_args__ = (UniqueConstraint("candidate_id", "evidence_type", name="uq_candidate_evidence_type"),)

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    placement_id = Column(MySQLCHAR(32), nullable=True, index=True)
    evidence_type = Column(String(30), nullable=False)  # location | photo | experience_letter | bank_statement
    file_path = Column(String(500), nullable=True)
    original_filename = Column(String(255), nullable=True)
    latitude = Column(String(20), nullable=True)
    longitude = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)