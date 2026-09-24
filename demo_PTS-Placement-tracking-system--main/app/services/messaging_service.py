"""Central place to send Email/SMS/WhatsApp/Voice Call and log every
attempt to CommunicationLog, which drives the Super Admin dashboard's
Calls Made / WhatsApp Delivered / SMS Delivered / Email Delivered cards
(SRS FR-02).

Email is real - it wraps app.utils.email.send_notification_email(), which
already sends via the configured SMTP server (organization override if
set, else platform-wide - SRS FR-14).

WhatsApp is real - it calls Meta's WhatsApp Cloud API directly (see
send_whatsapp() below). IMPORTANT LIMITATION: Meta's Cloud API only allows
free-form text messages within an active 24-hour customer-service window
(i.e. the candidate messaged this WhatsApp number recently). For
business-initiated messages outside that window - which is the normal case
for scheduled notifications like PLACEMENT_REMINDER - Meta requires a
pre-approved message TEMPLATE registered in Meta Business Manager, not
arbitrary text. This function currently sends free-form text via the
/messages endpoint. If sends start failing with Meta error code 131047
("re-engagement message outside allowed window") or similar, that is this
limitation - the call needs to switch to the template-message payload shape
(type="template") with an approved template name instead of type="text".
That requires deciding on and getting templates approved by Meta first, so
it is intentionally left as free-form text for now.

SMS and Voice Call are NOT wired to a real provider yet - no API key/URL is
configured (see .env: SMS_API_URL is blank), whether at the platform or
organization level. Calling these functions logs a 'not_configured' row so
the dashboard counts reflect reality (0 delivered) instead of fabricating
numbers, and returns False. To wire in a real provider later, replace the
body of the relevant function with the actual API call, keeping the
CommunicationLog.create(...) calls so logging keeps working - and pull
credentials via get_sms_config(organization_id) from
app.utils.platform_settings so the organization override (once configured)
is honored automatically.
"""

import logging
import os

import requests

from app.extensions import db
from app.models.communication_log import CommunicationLog
from app.models.organization import Organization
from app.utils.email import send_notification_email
from app.utils.platform_settings import (
    get_organization_channel_settings,
    get_whatsapp_config,
    is_channel_enabled,
)

logger = logging.getLogger(__name__)

# Meta's default Graph API base. Overridable via WHATSAPP_API_URL in .env in
# case that ever needs to point somewhere else (a self-hosted gateway,
# a specific pinned Graph API version, etc.) - blank means "use this default".
WHATSAPP_GRAPH_API_BASE = os.environ.get("WHATSAPP_API_URL") or "https://graph.facebook.com/v21.0"


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


def _org_uses_own_smtp(organization_id):
    """True if this organization saved its OWN SMTP server on the Channels
    page (host, username and password all present). Such an organization
    pays its own email provider, so no plan credit is used for its emails."""
    org_settings = get_organization_channel_settings(organization_id)
    return bool(
        org_settings
        and org_settings.smtp_host
        and org_settings.smtp_username
        and org_settings.smtp_password
    )


def _reserve_email_credit(organization_id):
    """Atomically takes one email credit; False if the balance is 0 / empty.
    A single UPDATE ... WHERE email_credits > 0, so two emails sent at the
    same moment can never both spend the last credit."""
    updated = Organization.query.filter(
        Organization.id == organization_id,
        Organization.email_credits > 0,
    ).update({Organization.email_credits: Organization.email_credits - 1}, synchronize_session=False)
    db.session.commit()
    return updated == 1


def _refund_email_credit(organization_id):
    Organization.query.filter(Organization.id == organization_id).update(
        {Organization.email_credits: Organization.email_credits + 1}, synchronize_session=False
    )
    db.session.commit()


def _reserve_whatsapp_credit(organization_id):
    """Same atomic pattern as _reserve_email_credit, for whatsapp_credits."""
    updated = Organization.query.filter(
        Organization.id == organization_id,
        Organization.whatsapp_credits > 0,
    ).update({Organization.whatsapp_credits: Organization.whatsapp_credits - 1}, synchronize_session=False)
    db.session.commit()
    return updated == 1


def _refund_whatsapp_credit(organization_id):
    Organization.query.filter(Organization.id == organization_id).update(
        {Organization.whatsapp_credits: Organization.whatsapp_credits + 1}, synchronize_session=False
    )
    db.session.commit()


def _org_uses_own_whatsapp(organization_id):
    """True if this organization saved its OWN WhatsApp API key + phone
    number ID on the Channels page. Mirrors _org_uses_own_smtp - an
    organization paying for its own WhatsApp number does not spend plan
    credits."""
    org_settings = get_organization_channel_settings(organization_id)
    return bool(
        org_settings
        and org_settings.whatsapp_api_key
        and org_settings.whatsapp_phone_number_id
    )


def _normalize_whatsapp_number(raw_number):
    """Strips everything but digits and assumes +91 (India) for a bare
    10-digit mobile number, since that's how candidate.mobile is stored
    throughout this app (no country code). Returns None if nothing usable
    is left."""
    digits = "".join(ch for ch in (raw_number or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def send_email(to_email, subject, body, organization_id=None, candidate_id=None, html_body=None):
    """Sends a real email via the configured SMTP server and logs the
    attempt. Returns True if sent, False if it failed (error is logged,
    not raised - callers should not have to wrap this in try/except for
    normal notification flows).

    organization_id (SRS FR-14): checked against this organization's own
    EMAIL on/off override (falls back to the platform-wide toggle if not
    set), and passed through to send_notification_email so that
    organization's own SMTP credentials are used if it has any configured.

    html_body (optional): when given, sends a styled HTML version of the
    email alongside the plain-text `body` fallback. When omitted, sends
    plain text only - existing callers are unaffected.

    Credits: an organization that sends through Codevocado's gateway (i.e.
    it has NOT saved its own SMTP server) uses one email credit from its
    plan per email. With no credits left the email is not sent and the
    attempt is logged as failed. An organization on its own SMTP server,
    and emails with no organization_id, do not use credits."""
    if not is_channel_enabled("EMAIL", organization_id):
        _log("email", to_email, "not_configured", organization_id, candidate_id, subject=subject,
             error_message="Email channel is disabled for this organization/platform.")
        return False

    charge_credit = bool(organization_id) and not _org_uses_own_smtp(organization_id)
    if charge_credit and not _reserve_email_credit(organization_id):
        _log("email", to_email, "failed", organization_id, candidate_id, subject=subject,
             error_message="No email credits left. Renew or upgrade the plan, or add your own SMTP server on the Channels page.")
        return False

    try:
        send_notification_email(to_email, subject, body, organization_id=organization_id, html_body=html_body)
        _log("email", to_email, "sent", organization_id, candidate_id, subject=subject)
        return True
    except Exception as exc:
        if charge_credit:
            _refund_email_credit(organization_id)
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
    """Sends a WhatsApp message via Meta's WhatsApp Cloud API (POST
    /{phone_number_id}/messages) and logs the attempt to CommunicationLog.
    Returns True if Meta accepted the message, False otherwise.

    See the module docstring for the important 24-hour session window /
    approved-template limitation before relying on this for real candidate
    notifications.

    Credits: mirrors send_email's credit logic - an organization using
    Codevocado's own WhatsApp number/credentials (i.e. it has NOT saved its
    own WhatsApp API key + phone number ID on the Channels page) spends one
    whatsapp_credit per message. No credits left -> message is not sent.
    An organization on its own WhatsApp number, and messages with no
    organization_id, do not use credits.
    """
    if not is_channel_enabled("WHATSAPP", organization_id):
        _log("whatsapp", to_number, "not_configured", organization_id, candidate_id,
             error_message="WhatsApp channel is disabled for this organization/platform.")
        return False

    access_token, phone_number_id = get_whatsapp_config(organization_id)
    if not access_token or not phone_number_id:
        _log("whatsapp", to_number, "not_configured", organization_id, candidate_id,
             error_message="WhatsApp is not configured (missing access token or phone number ID). "
                            "Set this on the super-admin Integrations page or this organization's Channel Settings.")
        return False

    clean_number = _normalize_whatsapp_number(to_number)
    if not clean_number:
        _log("whatsapp", to_number, "failed", organization_id, candidate_id,
             error_message="Invalid recipient number.")
        return False

    charge_credit = bool(organization_id) and not _org_uses_own_whatsapp(organization_id)
    if charge_credit and not _reserve_whatsapp_credit(organization_id):
        _log("whatsapp", to_number, "failed", organization_id, candidate_id,
             error_message="No WhatsApp credits left. Renew or upgrade the plan, or add your own WhatsApp number on the Channels page.")
        return False

    url = f"{WHATSAPP_GRAPH_API_BASE.rstrip('/')}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_number,
        "type": "text",
        "text": {"body": message, "preview_url": False},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        message_id = (data.get("messages") or [{}])[0].get("id")
        _log("whatsapp", to_number, "sent", organization_id, candidate_id,
             error_message=f"meta_message_id={message_id}" if message_id else None)
        return True
    except requests.exceptions.HTTPError:
        try:
            error_body = response.json().get("error", {})
        except Exception:
            error_body = {"message": response.text[:300] if response is not None else "unknown error"}
        error_code = error_body.get("code")
        error_detail = f"[{error_code}] {error_body.get('message', '')}".strip()
        if charge_credit:
            _refund_whatsapp_credit(organization_id)
        logger.warning("messaging_service: whatsapp to %s failed (%s)", to_number, error_detail)
        _log("whatsapp", to_number, "failed", organization_id, candidate_id, error_message=error_detail[:500])
        return False
    except requests.exceptions.RequestException as exc:
        if charge_credit:
            _refund_whatsapp_credit(organization_id)
        logger.warning("messaging_service: whatsapp to %s failed - network error (%s)", to_number, exc)
        _log("whatsapp", to_number, "failed", organization_id, candidate_id, error_message=str(exc)[:500])
        return False


def make_call(to_number, organization_id=None, candidate_id=None):
    """No voice call provider is configured yet. Logs a not_configured
    attempt and returns False. Replace this body with a real voice API
    call (e.g. Exotel, Twilio Voice) once configured."""
    _log("voice_call", to_number, "not_configured", organization_id, candidate_id)
    return False