import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CandidateTrustedDevice(db.Model):
    """A 'remembered' browser for a candidate, so they can skip the login
    OTP for 30 days on that device. Only a hash of the device token is
    stored here - the raw token lives only in the candidate's cookie."""

    __tablename__ = "candidate_trusted_devices"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def is_valid(self):
        return datetime.utcnow() <= self.expires_at
