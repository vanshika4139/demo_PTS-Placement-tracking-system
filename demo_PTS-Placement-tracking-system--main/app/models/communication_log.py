import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CommunicationLog(db.Model):
    """Records every attempt to reach someone via Email, SMS, WhatsApp, or
    Voice Call - regardless of whether the channel is wired to a real
    provider yet. Drives the Super Admin dashboard's Calls Made / WhatsApp
    Delivered / SMS Delivered / Email Delivered cards (SRS FR-02).

    Channels without a real provider yet (sms, whatsapp, voice_call) log
    status='not_configured' via app/services/messaging_service.py until a
    real provider is wired in - see that module's docstring.
    """

    __tablename__ = "communication_logs"

    CHANNELS = ("email", "sms", "whatsapp", "voice_call")
    STATUSES = ("sent", "delivered", "failed", "not_configured")

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=True, index=True)
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=True, index=True)
    channel = Column(String(20), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
