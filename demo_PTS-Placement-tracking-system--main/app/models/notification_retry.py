import uuid

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CommunicationTransaction(db.Model):
    """Every change to an organization's email/WhatsApp credits, with balance before and after (FR-46)."""

    __tablename__ = "communication_transactions"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, nullable=False, index=True)
    channel = Column(String(20), nullable=False)
    change = Column(Integer, nullable=False)  # -1 used, +1 refunded
    balance_before = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    reason = Column(String(60), nullable=False)  # sent | refund
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)


class NotificationRetry(db.Model):
    """A failed email/WhatsApp waiting to be retried with exponential backoff (FR-28, NFR-07)."""

    __tablename__ = "notification_retries"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, nullable=True, index=True)
    candidate_id = Column(MySQLCHAR(32), nullable=True)
    channel = Column(String(20), nullable=False)  # email | whatsapp
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending | sent | failed
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)