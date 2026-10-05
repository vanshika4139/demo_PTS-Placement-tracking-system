import os
import smtplib
import ssl
import uuid
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html as _html
import re
from email.utils import formataddr, formatdate, make_msgid, parseaddr

import requests

from app.extensions import db
from app.models.email_log import EmailLog, classify_email_type
from app.utils.platform_settings import get_smtp_config, is_channel_enabled

# Seconds to wait for the SMTP server before giving up. Without a timeout a
# dead/slow SMTP server hangs the whole web request (or the scheduler thread).
SMTP_TIMEOUT = int(os.environ.get("SMTP_TIMEOUT", "20") or "20")


class EmailChannelDisabled(RuntimeError):
    """Raised (and logged as a failed EmailLog row) when the Email channel is
    switched off for the platform / organization."""


def _log_email(to_email, subject, status, error_message=None, organization_id=None,
                candidate_id=None, user_id=None, has_attachment=False, email_type=None):
    """Writes one row to email_logs. Never raises - a logging failure
    should never break the caller's email-sending flow."""
    try:
        log = EmailLog(
            id=uuid.uuid4().hex,
            to_email=to_email,
            subject=subject,
            status=status,
            error_message=error_message,
            organization_id=str(organization_id) if organization_id else None,
            candidate_id=candidate_id,
            user_id=user_id,
            has_attachment=has_attachment,
            email_type=email_type or classify_email_type(subject),
            created_at=datetime.utcnow(),
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


BRAND_NAME = os.environ.get("EMAIL_BRAND_NAME", "Codevocado")
BRAND_TAGLINE = os.environ.get("EMAIL_BRAND_TAGLINE", "Placement Tracking System")
FROM_NAME = os.environ.get("EMAIL_FROM_NAME", f"{BRAND_NAME} Placement Tracking")


def _from_header(address):
    """'Codevocado Placement Tracking <user@example.com>' instead of a bare address."""
    if not address:
        return address
    return formataddr((FROM_NAME, address))


def _msgid(address):
    """Message-ID on the sender's own domain (looks more legitimate than the PC's hostname)."""
    domain = address.split("@", 1)[1] if address and "@" in address else None
    return make_msgid(domain=domain)


def _email_shell(title, inner_html):
    """Branded, email-client-safe (table + inline CSS) HTML wrapper."""
    brand = _html.escape(BRAND_NAME)
    tagline = _html.escape(BRAND_TAGLINE)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f'<title>{_html.escape(title or brand)}</title></head>'
        '<body style="margin:0;padding:0;background:#f3f4f6;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f3f4f6;padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;'
        'border:1px solid #e5e7eb;font-family:Segoe UI,Arial,sans-serif;">'
        '<tr><td style="background:#1f2937;padding:18px 24px;color:#ffffff;">'
        f'<div style="font-size:18px;font-weight:700;">{brand}</div>'
        f'<div style="font-size:12px;color:#d1d5db;margin-top:2px;">{tagline}</div></td></tr>'
        '<tr><td style="padding:28px 24px 12px 24px;color:#111827;font-size:15px;line-height:1.6;">'
        f'{inner_html}</td></tr>'
        '<tr><td style="padding:16px 24px 24px 24px;color:#6b7280;font-size:12px;line-height:1.5;'
        'border-top:1px solid #f3f4f6;">'
        f'This is an automated message from {brand} {tagline}. '
        'If you did not expect it, you can ignore it.</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def _wrap_html(subject, body):
    """Turns a plain-text notification into a branded HTML email."""
    text = _html.escape(body or "")
    text = re.sub(r'(https?://[^\s<]+)', r'<a href="\1" style="color:#2563eb;">\1</a>', text)
    text = text.replace("\r\n", "\n").replace("\n", "<br>")
    inner = (
        f'<h2 style="margin:0 0 16px 0;font-size:18px;color:#111827;">{_html.escape(subject or "")}</h2>'
        f'<div>{text}</div>'
    )
    return _email_shell(subject, inner)


def _otp_html(otp_code):
    inner = (
        '<h2 style="margin:0 0 12px 0;font-size:18px;color:#111827;">Password reset</h2>'
        '<p style="margin:0 0 8px 0;">Use this one-time password (OTP) to reset your password:</p>'
        '<div style="text-align:center;margin:22px 0;">'
        '<span style="display:inline-block;font-size:30px;letter-spacing:8px;font-weight:700;'
        'color:#1f2937;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:8px;padding:12px 22px;">'
        f'{_html.escape(str(otp_code))}</span></div>'
        '<p style="margin:0;">This OTP is valid for 10 minutes. If you did not request it, '
        'please ignore this email. Never share this OTP with anyone.</p>'
    )
    return _email_shell("Password reset OTP", inner)


def _from_address(smtp_username):
    """Providers like SendGrid/SES use a non-email username ("apikey"), which
    is not a valid From address. Use SMTP_FROM_EMAIL (.env) in that case."""
    if smtp_username and "@" in smtp_username:
        return smtp_username
    return os.environ.get("SMTP_FROM_EMAIL") or smtp_username


def _open_smtp(host, port, username, password):
    """Port 465 = implicit SSL. Any other port = plain connect + STARTTLS
    (refuses to log in over an unencrypted connection)."""
    port = int(port)
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
        try:
            server.ehlo()
            if not server.has_extn("starttls"):
                raise smtplib.SMTPException(
                    f"SMTP server {host}:{port} does not support STARTTLS - refusing to send credentials unencrypted."
                )
            server.starttls(context=context)
            server.ehlo()
        except Exception:
            server.close()
            raise
    try:
        server.login(username, password)
    except Exception:
        server.close()
        raise
    return server


def _build_message(from_addr, to_email, subject, body, html_body=None, attachments=None):
    if not html_body:
        html_body = _wrap_html(subject, body)

    if not (html_body or attachments):
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = _from_header(from_addr)
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = _msgid(from_addr)
        return msg

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = _from_header(from_addr)
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = _msgid(from_addr)

    # Text/HTML body goes in its own "alternative" sub-part so mail clients
    # pick whichever they can render, independent of attachments.
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        body_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body_part)

    for att in (attachments or []):
        filename = att.get("filename")
        if not filename:
            raise ValueError("Each attachment needs a 'filename'")

        if "data" in att:
            file_bytes = att["data"]
        elif "path" in att:
            with open(att["path"], "rb") as f:
                file_bytes = f.read()
        else:
            raise ValueError("Each attachment needs either 'data' or 'path'")

        part = MIMEApplication(file_bytes, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)
    return msg


def _org_has_own_smtp(organization_id):
    """True if this organization saved its OWN complete SMTP server (host,
    username and password). Such emails must keep using that SMTP, not the
    platform gateway (same rule as messaging_service._org_uses_own_smtp)."""
    if not organization_id:
        return False
    try:
        from app.utils.platform_settings import get_organization_channel_settings
        s = get_organization_channel_settings(organization_id)
    except Exception:
        return False
    return bool(s and s.smtp_host and s.smtp_username and s.smtp_password)


def _send_via_gateway(to_email, subject, body, html_body):
    """Sends through the REST email gateway configured in .env
    (EMAIL_API_URL, EMAIL_API_KEY, EMAIL_FROM). Raises on any failure so
    _dispatch logs it to email_logs."""
    url = os.environ.get("EMAIL_API_URL")
    key = os.environ.get("EMAIL_API_KEY")
    sender = os.environ.get("EMAIL_FROM")
    payload = {"from": sender, "to": to_email, "subject": subject, "text": body}
    if html_body:
        payload["html"] = html_body
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=SMTP_TIMEOUT,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Email gateway error {resp.status_code}: {resp.text[:200]}")


def _dispatch(to_email, subject, body, html_body, attachments, organization_id,
              candidate_id, user_id, essential):
    """Single code path for every outgoing email. Everything that can fail
    (channel disabled, SMTP not configured, bad attachment, network, login)
    happens inside the try, so EVERY failure is written to email_logs."""
    has_attachment = bool(attachments)
    try:
        if not essential and not is_channel_enabled("EMAIL", organization_id):
            raise EmailChannelDisabled(
                "Email channel is disabled for this organization/platform "
                "(Integrations page or the organization's Channel Settings)."
            )

        use_gateway = (
            bool(os.environ.get("EMAIL_API_KEY") and os.environ.get("EMAIL_API_URL"))
            and not attachments
            and not _org_has_own_smtp(organization_id)
        )

        if use_gateway:
            _send_via_gateway(to_email, subject, body, html_body or _wrap_html(subject, body))
        else:
            host, port, username, password = get_smtp_config(organization_id)
            msg = _build_message(_from_address(username), to_email, subject, body, html_body, attachments)

            server = _open_smtp(host, port, username, password)
            try:
                server.sendmail(parseaddr(msg["From"])[1] or msg["From"], [to_email], msg.as_string())
            finally:
                try:
                    server.quit()
                except Exception:
                    server.close()
    except Exception as exc:
        _log_email(
            to_email, subject, status="failed", error_message=str(exc),
            organization_id=organization_id, candidate_id=candidate_id,
            user_id=user_id, has_attachment=has_attachment,
        )
        raise

    _log_email(
        to_email, subject, status="sent",
        organization_id=organization_id, candidate_id=candidate_id,
        user_id=user_id, has_attachment=has_attachment,
    )


def send_otp_email(to_email: str, otp_code: str) -> None:
    """Send a password-reset / login OTP. Raises on failure so the caller can
    show an error.

    Always uses platform-wide SMTP (no organization_id). It is marked
    `essential`, so it is still sent when the Email channel toggle is off -
    switching notifications off must never lock people out of logging in."""
    subject = "Your Codevocado Password Reset OTP"
    body = (
        f"Your OTP for resetting your Codevocado password is: {otp_code}\n\n"
        f"This OTP is valid for 10 minutes. If you did not request this, please ignore this email."
    )
    _dispatch(to_email, subject, body, _otp_html(otp_code), None, None, None, None, essential=True)


def send_notification_email(
    to_email: str,
    subject: str,
    body: str,
    organization_id=None,
    html_body: str = None,
    attachments: list = None,
    candidate_id=None,
    user_id=None,
    essential: bool = False,
) -> None:
    """Send a notification email. Raises on failure - callers should wrap
    this in try/except so an email failure never breaks the main request.

    - The Email channel on/off toggle is enforced here (organization override
      first, then platform). Pass essential=True to bypass it.
    - organization_id: uses that organization's own SMTP server if it saved a
      complete one (host + username + password), else platform-wide SMTP.
    - html_body: adds an HTML alternative next to the plain-text body.
    - attachments: list of {"path": ..., "filename": ...} or
      {"data": <bytes>, "filename": ...}.
    - candidate_id / user_id: who the email relates to (email_logs audit).
    """
    _dispatch(to_email, subject, body, html_body, attachments, organization_id,
              candidate_id, user_id, essential)
