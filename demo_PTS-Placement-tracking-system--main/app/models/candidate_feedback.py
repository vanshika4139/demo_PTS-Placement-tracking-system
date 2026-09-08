import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CandidateFeedback(db.Model):
    """1-5 star rating + optional comment, collected once from the candidate
    dashboard after placement. organization_id is denormalized so org admins
    can list/filter feedback without a join on every request.
    unique=True on candidate_id enforces one submission per candidate."""

    __tablename__ = "candidate_feedback"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, unique=True, index=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    rating = Column(SmallInteger, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)