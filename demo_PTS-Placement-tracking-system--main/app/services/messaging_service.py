"""Central place to send Email/SMS/WhatsApp/Voice Call and log every
attempt to CommunicationLog, which drives the Super Admin dashboard's
Calls Made / WhatsApp Delivered / SMS Delivered / Email Delivered cards
(SRS FR-02).

Email is real - it wraps app.utils.email.send_notification_email(), which
already sends via the configured SMTP server (organization override if
set, else platform-wide - SRS FR-14).

SMS, WhatsApp, and Voice Call are NOT wired to a real provider yet - no
API key/URL is configured (see .env: SMS_API_URL, WHATSAPP_API_URL are
blank), whether at the platform or organization level. Calling these
functions logs a 'not_configured' row so the dashboard counts reflect
reality (0 delivered) instead of fabricating numbers, and returns False.
To wire in a real provider later, replace the body of the relevant
function with the actual API call, keeping the CommunicationLog.create(...)
calls so logging keeps working - and pull credentials via
get_whatsapp_config(organization_id)/get_sms_config(organization_id) from
app.utils.platform_settings so the organization override (once configured)
is honored automatically.
"""

import logging

from app.extensions import db
from app.models.communication_log import CommunicationLog
from app.utils.email import send_notification_email
from app.utils.platform_settings import is_channel_enabled

logger = logging.getLogger(__name__)


def _log(channel, recipient, status, organization_id=None, candidate_id=None, subject=None, error_message=None):
    entry = CommunicationLog(
        organization_id=organization_id,
        candidate_id=candidate_id,
        channel=channel,
        recipient=recipient,
        subject=subject,
        status=status,
        error_message=error_message,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def send_email(to_email, subject, body, organization_id=None, candidate_id=None):
    """Sends a real email via the configured SMTP server and logs the
    attempt. Returns True if sent, False if it failed (error is logged,
    not raised - callers should not have to wrap this in try/except for
    normal notification flows).

    organization_id (SRS FR-14): checked against this organization's own
    EMAIL on/off override (falls back to the platform-wide toggle if not
    set), and passed through to send_notification_email so that
    organization's own SMTP credentials are used if it has any configured."""
    if not is_channel_enabled("EMAIL", organization_id):
        _log("email", to_email, "not_configured", organization_id, candidate_id, subject=subject,
             error_message="Email channel is disabled for this organization/platform.")
        return False

    try:
        send_notification_email(to_email, subject, body, organization_id=organization_id)
        _log("email", to_email, "sent", organization_id, candidate_id, subject=subject)
        return True
    except Exception as exc:
        logger.warning("messaging_service: email to %s failed (%s)", to_email, exc)
        _log("email", to_email, "failed", organization_id, candidate_id, subject=subject, error_message=str(exc))
        return False


def send_sms(to_number, message, organization_id=None, candidate_id=None):
    """No SMS provider is configured yet (.env SMS_API_URL is blank), at
    either the platform or organization level. Logs a not_configured
    attempt and returns False. Replace this body with a real API call
    once a provider (e.g. Twilio, MSG91) is set up - use
    get_sms_config(organization_id) from app.utils.platform_settings to
    pick up an organization's own credentials if it has any configured."""
    _log("sms", to_number, "not_configured", organization_id, candidate_id)
    return False


def send_whatsapp(to_number, message, organization_id=None, candidate_id=None):
    """No WhatsApp provider is configured yet (.env WHATSAPP_API_URL is
    blank), at either the platform or organization level. Logs a
    not_configured attempt and returns False. Replace this body with a
    real WhatsApp Business API call once configured - use
    get_whatsapp_config(organization_id) from app.utils.platform_settings
    to pick up an organization's own credentials if it has any configured."""
    _log("whatsapp", to_number, "not_configured", organization_id, candidate_id)
    return False


def make_call(to_number, organization_id=None, candidate_id=None):
    """No voice call provider is configured yet. Logs a not_configured
    attempt and returns False. Replace this body with a real voice API
    call (e.g. Exotel, Twilio Voice) once configured."""
    _log("voice_call", to_number, "not_configured", organization_id, candidate_id)
    return False