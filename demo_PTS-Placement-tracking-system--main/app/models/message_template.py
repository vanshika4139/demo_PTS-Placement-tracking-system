import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class MessageTemplate(db.Model):
    """A reusable message template for a specific notification purpose and
    channel (SRS FR-15). E.g. a PLACEMENT_REMINDER template for the EMAIL
    channel, and a separate one for SMS - same purpose, different wording
    per channel.

    body/subject may contain placeholders like {candidate_name},
    {employer_name}, {joining_date} - resolved by whatever code renders the
    template before calling app.services.messaging_service.
    """

    __tablename__ = "message_templates"

    TEMPLATE_TYPES = (
        "PLACEMENT_REMINDER",
        "SALARY_UPDATE",
        "VERIFICATION_REQUEST",
        "SURVEY",
        "ANNIVERSARY",
        "OFFER_LETTER",
    )
    CHANNELS = ("EMAIL", "WHATSAPP", "SMS", "VOICE_CALL", "PUSH")

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    template_type = Column(String(40), nullable=False)
    channel = Column(String(20), nullable=False)
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
