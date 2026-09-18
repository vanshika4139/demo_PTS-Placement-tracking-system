"""
Platform-wide integration settings (SMTP, WhatsApp, SMS), stored in the
single-row platform_settings table so the super admin can manage these
credentials from the UI instead of editing .env by hand.

Falls back to environment variables wherever a DB field is blank, so nothing
breaks if the row hasn't been filled in yet - .env keeps working as the
default, the DB just overrides it once someone saves the settings form.

SRS FR-14 (per-organization channel configuration): SMTP/WhatsApp/SMS can
also be overridden per-organization via OrganizationChannelSettings (one
row per organization, all fields nullable). Fallback order everywhere in
this module is: organization override -> platform-wide DB settings -> .env.
Callers that don't pass an organization_id get the exact same behavior as
before (platform-wide -> .env).
"""

import os

from app.extensions import db
from app.models import PlatformSettings, OrganizationChannelSettings


def get_platform_settings():
    """Returns the single settings row, creating it (empty) if it doesn't exist yet."""
    settings = PlatformSettings.query.get("platform")
    if settings is None:
        settings = PlatformSettings(id="platform")
        db.session.add(settings)
        db.session.commit()
    return settings


def get_organization_channel_settings(organization_id):
    """Returns the per-organization channel settings row, creating it
    (empty) if it doesn't exist yet. Every field on this row is nullable -
    blank means 'inherit the platform-wide setting' (see get_smtp_config,
    get_whatsapp_config, get_sms_config below for how the fallback works)."""
    if not organization_id:
        return None
    settings = OrganizationChannelSettings.query.filter_by(organization_id=organization_id).first()
    if settings is None:
        settings = OrganizationChannelSettings(organization_id=organization_id)
        db.session.add(settings)
        db.session.commit()
    return settings


def get_smtp_config(organization_id=None):
    """Returns (host, port, username, password). Fallback order: this
    organization's own SMTP override (if organization_id is given and it
    has one set) -> platform-wide DB settings -> .env. Passing no
    organization_id (or an organization with no override) behaves exactly
    as before - platform-wide settings, falling back to .env."""
    org_settings = get_organization_channel_settings(organization_id) if organization_id else None

    platform = get_platform_settings()

    host = (org_settings.smtp_host if org_settings else None) or platform.smtp_host or os.environ.get("SMTP_HOST", "")
    port = (org_settings.smtp_port if org_settings else None) or platform.smtp_port or int(os.environ.get("SMTP_PORT", "587") or "587")
    username = (org_settings.smtp_username if org_settings else None) or platform.smtp_username or os.environ.get("SMTP_USERNAME", "")
    password = (org_settings.smtp_password if org_settings else None) or platform.smtp_password or os.environ.get("SMTP_PASSWORD", "")

    if not host or not username or not password:
        raise RuntimeError(
            "SMTP is not configured - set it on the super-admin Integrations "
            "page (or this organization's Channel Settings), or via .env "
            "(SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD)."
        )

    return host, port, username, password


def get_whatsapp_config(organization_id=None):
    """Returns (api_key, phone_number_id). Fallback order: organization
    override -> platform-wide -> .env."""
    org_settings = get_organization_channel_settings(organization_id) if organization_id else None
    platform = get_platform_settings()

    api_key = (org_settings.whatsapp_api_key if org_settings else None) or platform.whatsapp_api_key or os.environ.get("WHATSAPP_API_KEY", "")
    phone_number_id = (org_settings.whatsapp_phone_number_id if org_settings else None) or platform.whatsapp_phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    return api_key, phone_number_id


def get_sms_config(organization_id=None):
    """Returns (api_key, sender_id). Fallback order: organization override
    -> platform-wide -> .env."""
    org_settings = get_organization_channel_settings(organization_id) if organization_id else None
    platform = get_platform_settings()

    api_key = (org_settings.sms_api_key if org_settings else None) or platform.sms_api_key or os.environ.get("SMS_API_KEY", "")
    sender_id = (org_settings.sms_sender_id if org_settings else None) or platform.sms_sender_id or os.environ.get("SMS_SENDER_ID", "")
    return api_key, sender_id


def get_voice_call_config():
    """Returns (provider, api_key, caller_id) - DB values win, .env is the fallback.
    No per-organization override yet - voice call has no real provider wired
    at the platform level either, so there's nothing meaningful to override."""
    settings = get_platform_settings()
    provider = settings.voice_provider or os.environ.get("VOICE_CALL_PROVIDER", "")
    api_key = settings.voice_api_key or os.environ.get("VOICE_CALL_API_KEY", "")
    caller_id = settings.voice_caller_id or os.environ.get("VOICE_CALL_CALLER_ID", "")
    return provider, api_key, caller_id


def get_push_config():
    """Returns (provider, server_key, sender_id) - DB values win, .env is the fallback.
    No per-organization override yet - same reasoning as get_voice_call_config."""
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

# Organization-level enabled/disabled override field names (mirrors
# CHANNEL_ENABLED_FIELD above, but only for the channels that support a
# per-organization override - see OrganizationChannelSettings).
ORG_CHANNEL_ENABLED_FIELD = {
    "EMAIL": "email_enabled",
    "WHATSAPP": "whatsapp_enabled",
    "SMS": "sms_enabled",
}


def is_channel_enabled(channel_type, organization_id=None):
    """True if this channel is switched on. If organization_id is given
    and that organization has explicitly set this channel on/off
    (True/False, not None), that decision wins. Otherwise falls back to
    the platform-wide toggle, exactly as before."""
    org_field = ORG_CHANNEL_ENABLED_FIELD.get(channel_type)
    if organization_id and org_field:
        org_settings = get_organization_channel_settings(organization_id)
        org_value = getattr(org_settings, org_field, None)
        if org_value is not None:
            return bool(org_value)

    settings = get_platform_settings()
    field = CHANNEL_ENABLED_FIELD.get(channel_type)
    return bool(getattr(settings, field, False)) if field else False


STRING_FIELDS = (
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "whatsapp_api_key", "whatsapp_phone_number_id",
    "sms_api_key", "sms_sender_id",
    "voice_provider", "voice_api_key", "voice_caller_id",
    "push_provider", "push_server_key", "push_sender_id",
    "payment_gateway_provider", "payment_gateway_key_id",
    "payment_gateway_key_secret", "payment_gateway_webhook_secret",
)

BOOL_FIELDS = (
    "email_enabled", "whatsapp_enabled", "sms_enabled",
    "voice_call_enabled", "push_enabled", "payment_gateway_enabled",
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


ORG_STRING_FIELDS = (
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "whatsapp_api_key", "whatsapp_phone_number_id",
    "sms_api_key", "sms_sender_id",
)

ORG_BOOL_FIELDS = ("email_enabled", "whatsapp_enabled", "sms_enabled")


def update_organization_channel_settings(organization_id, fields, actor_id=None):
    """Updates only the keys present in `fields` for one organization's
    channel override row. Pass an empty string for any string field to
    clear it (falls back to platform-wide again). Pass None (not present
    in `fields`, or explicitly None) for a bool field to clear the
    override and inherit the platform-wide on/off toggle again - this is
    different from update_platform_settings, where a missing checkbox
    always means False, because here 'not overriding' is a real third
    state distinct from 'overriding to off'."""
    settings = get_organization_channel_settings(organization_id)

    for key in ORG_STRING_FIELDS:
        if key in fields:
            value = fields[key]
            if key == "smtp_port":
                value = int(value) if value else None
            setattr(settings, key, value or None)

    for key in ORG_BOOL_FIELDS:
        if key in fields:
            setattr(settings, key, fields[key])  # True / False / None (inherit)

    settings.modified_by = actor_id
    db.session.commit()
    return settings