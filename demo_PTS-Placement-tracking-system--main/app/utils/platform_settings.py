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


def get_voice_call_config():
    """Returns (provider, api_key, caller_id) - DB values win, .env is the fallback."""
    settings = get_platform_settings()
    provider = settings.voice_provider or os.environ.get("VOICE_CALL_PROVIDER", "")
    api_key = settings.voice_api_key or os.environ.get("VOICE_CALL_API_KEY", "")
    caller_id = settings.voice_caller_id or os.environ.get("VOICE_CALL_CALLER_ID", "")
    return provider, api_key, caller_id


def get_push_config():
    """Returns (provider, server_key, sender_id) - DB values win, .env is the fallback."""
    settings = get_platform_settings()
    provider = settings.push_provider or os.environ.get("PUSH_PROVIDER", "")
    server_key = settings.push_server_key or os.environ.get("PUSH_SERVER_KEY", "")
    sender_id = settings.push_sender_id or os.environ.get("PUSH_SENDER_ID", "")
    return provider, server_key, sender_id


# Maps a channel type (matches KycDocument-style upper-case constants used
# elsewhere in the app) to the PlatformSettings column that toggles it.
CHANNEL_ENABLED_FIELD = {
    "EMAIL": "email_enabled",
    "WHATSAPP": "whatsapp_enabled",
    "SMS": "sms_enabled",
    "VOICE_CALL": "voice_call_enabled",
    "PUSH": "push_enabled",
}


def is_channel_enabled(channel_type):
    """True if the super admin has switched this channel on. Message
    Templates and Notification Scheduling (built on top of this) should
    check this before attempting to send anything on a channel."""
    settings = get_platform_settings()
    field = CHANNEL_ENABLED_FIELD.get(channel_type)
    return bool(getattr(settings, field, False)) if field else False


STRING_FIELDS = (
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "whatsapp_api_key", "whatsapp_phone_number_id",
    "sms_api_key", "sms_sender_id",
    "voice_provider", "voice_api_key", "voice_caller_id",
    "push_provider", "push_server_key", "push_sender_id",
)

BOOL_FIELDS = (
    "email_enabled", "whatsapp_enabled", "sms_enabled",
    "voice_call_enabled", "push_enabled",
)


def update_platform_settings(fields, actor_id=None):
    """Updates only the keys present in `fields` (a dict). Pass an empty
    string for any string field to clear a stored value and fall back to
    .env again - fields are never required to be non-empty. Boolean
    enabled-toggle fields are set directly to whatever truthy/falsy value
    is passed in (checkboxes: True if checked, False if omitted)."""
    settings = get_platform_settings()

    for key in STRING_FIELDS:
        if key in fields:
            value = fields[key]
            if key == "smtp_port":
                value = int(value) if value else None
            setattr(settings, key, value or None)

    for key in BOOL_FIELDS:
        if key in fields:
            setattr(settings, key, bool(fields[key]))

    settings.modified_by = actor_id
    db.session.commit()
    return settings