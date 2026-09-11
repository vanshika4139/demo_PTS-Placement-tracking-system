import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class PlatformSettings(db.Model):
    """Platform-wide integration settings (SMTP, WhatsApp, SMS, Payment
    Gateway), editable by the super admin from the UI instead of hand-editing
    .env.

    This is a SINGLE-ROW table: there is always exactly one settings row
    (id="platform"), fetched/created via app.utils.platform_settings.

    Secrets stored here (smtp_password, whatsapp_api_key, sms_api_key,
    payment_gateway_key_secret, etc.) are plaintext in the database, same
    trust level as they'd have in .env - this table does not add encryption.
    Treat DB access accordingly.
    """

    __tablename__ = "platform_settings"

    id = Column(MySQLCHAR(32), primary_key=True, default="platform")

    # --- Email (SMTP) ---
    email_enabled = Column(Boolean, nullable=False, default=False)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)

    # --- WhatsApp ---
    whatsapp_enabled = Column(Boolean, nullable=False, default=False)
    whatsapp_api_key = Column(String(500), nullable=True)
    whatsapp_phone_number_id = Column(String(100), nullable=True)

    # --- SMS ---
    sms_enabled = Column(Boolean, nullable=False, default=False)
    sms_api_key = Column(String(500), nullable=True)
    sms_sender_id = Column(String(50), nullable=True)

    # --- Voice Call ---
    voice_call_enabled = Column(Boolean, nullable=False, default=False)
    voice_provider = Column(String(100), nullable=True)
    voice_api_key = Column(String(500), nullable=True)
    voice_caller_id = Column(String(50), nullable=True)

    # --- Push Notification ---
    push_enabled = Column(Boolean, nullable=False, default=False)
    push_provider = Column(String(100), nullable=True)
    push_server_key = Column(String(500), nullable=True)
    push_sender_id = Column(String(100), nullable=True)

    # --- Payment Gateway (FR-09) ---
    payment_gateway_enabled = Column(Boolean, nullable=False, default=False)
    payment_gateway_provider = Column(String(20), nullable=True)  # "razorpay" | "cashfree" | "stripe"
    payment_gateway_key_id = Column(String(255), nullable=True)       # Razorpay key_id / Cashfree app_id / Stripe publishable key
    payment_gateway_key_secret = Column(String(500), nullable=True)   # Razorpay key_secret / Cashfree secret_key / Stripe secret key
    payment_gateway_webhook_secret = Column(String(500), nullable=True)  # used to verify inbound webhook signatures

    modified_by = Column(MySQLCHAR(32), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)