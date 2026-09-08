"""
Platform-wide integration settings (SMTP, WhatsApp, SMS), stored in the
single-row platform_settings table so the super admin can manage these
credentials from the UI instead of editing .env by hand.

Falls back to environment variables wherever a DB field is blank, so nothing
breaks if the row hasn't been filled in yet - .env keeps working as the
default, the DB just overrides it once someone saves the settings form.
"""

import os

from app.extensions import db
from app.models import PlatformSettings


def get_platform_settings():
    """Returns the single settings row, creating it (empty) if it doesn't exist yet."""
    settings = PlatformSettings.query.get("platform")
    if settings is None:
        settings = PlatformSettings(id="platform")
        db.session.add(settings)
        db.session.commit()
    return settings


def get_smtp_config():
    """Returns (host, port, username, password) - DB values win, .env is the fallback."""
    settings = get_platform_settings()

    host = settings.smtp_host or os.environ.get("SMTP_HOST", "")
    port = settings.smtp_port or int(os.environ.get("SMTP_PORT", "587") or "587")
    username = settings.smtp_username or os.environ.get("SMTP_USERNAME", "")
    password = settings.smtp_password or os.environ.get("SMTP_PASSWORD", "")

    if not host or not username or not password:
        raise RuntimeError(
            "SMTP is not configured - set it on the super-admin Integrations "
            "page, or via .env (SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD)."
        )

    return host, port, username, password


def get_whatsapp_config():
    """Returns (api_key, phone_number_id) - DB values win, .env is the fallback."""
    settings = get_platform_settings()
    api_key = settings.whatsapp_api_key or os.environ.get("WHATSAPP_API_KEY", "")
    phone_number_id = settings.whatsapp_phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    return api_key, phone_number_id


def get_sms_config():
    """Returns (api_key, sender_id) - DB values win, .env is the fallback."""
    settings = get_platform_settings()
    api_key = settings.sms_api_key or os.environ.get("SMS_API_KEY", "")
    sender_id = settings.sms_sender_id or os.environ.get("SMS_SENDER_ID", "")
    return api_key, sender_id


def update_platform_settings(fields, actor_id=None):
    """Updates only the keys present in `fields` (a dict). Pass an empty
    string for any field to clear a stored value and fall back to .env
    again - fields are never required to be non-empty."""
    settings = get_platform_settings()

    for key in (
        "smtp_host", "smtp_port", "smtp_username", "smtp_password",
        "whatsapp_api_key", "whatsapp_phone_number_id",
        "sms_api_key", "sms_sender_id",
    ):
        if key in fields:
            value = fields[key]
            if key == "smtp_port":
                value = int(value) if value else None
            setattr(settings, key, value or None)

    settings.modified_by = actor_id
    db.session.commit()
    return settings