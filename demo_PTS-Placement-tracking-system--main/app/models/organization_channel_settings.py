from sqlalchemy import Column, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class OrganizationChannelSettings(db.Model):
    """Per-organization override of the platform-wide notification channel
    settings (SRS FR-14: 'platform AND organization level'). Every field is
    nullable and blank by default - a blank/None value means 'inherit from
    the platform-wide setting', matching the same fallback pattern
    PlatformSettings already uses for .env (see app/utils/platform_settings.py).

    One row per organization, created lazily the first time someone opens
    that organization's channel settings page (see get_organization_channel_settings())."""

    __tablename__ = "organization_channel_settings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, unique=True, index=True)

    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    email_enabled = Column(Boolean, nullable=True)  # None = inherit platform setting

    whatsapp_api_key = Column(String(255), nullable=True)
    whatsapp_phone_number_id = Column(String(100), nullable=True)
    whatsapp_enabled = Column(Boolean, nullable=True)

    sms_api_key = Column(String(255), nullable=True)
    sms_sender_id = Column(String(50), nullable=True)
    sms_enabled = Column(Boolean, nullable=True)

    modified_at = Column(DateTime, nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)  # matches User.id's UUID-hex type
    created_at = Column(DateTime, server_default=func.now(), nullable=False)