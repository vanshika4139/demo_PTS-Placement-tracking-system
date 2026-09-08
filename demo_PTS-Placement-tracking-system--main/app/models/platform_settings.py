import uuid

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class PlatformSettings(db.Model):
    """Platform-wide integration settings (SMTP, WhatsApp, SMS), editable by
    the super admin from the UI instead of hand-editing .env.

    This is a SINGLE-ROW table: there is always exactly one settings row
    (id="platform"), fetched/created via app.utils.platform_settings.

    Secrets stored here (smtp_password, whatsapp_api_key, sms_api_key) are
    plaintext in the database, same trust level as they'd have in .env - this
    table does not add encryption. Treat DB access accordingly.
    """

    __tablename__ = "platform_settings"

    id = Column(MySQLCHAR(32), primary_key=True, default="platform")

    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)

    whatsapp_api_key = Column(String(500), nullable=True)
    whatsapp_phone_number_id = Column(String(100), nullable=True)

    sms_api_key = Column(String(500), nullable=True)
    sms_sender_id = Column(String(50), nullable=True)

    modified_by = Column(MySQLCHAR(32), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)