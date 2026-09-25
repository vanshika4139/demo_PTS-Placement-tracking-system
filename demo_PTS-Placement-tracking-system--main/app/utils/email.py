import uuid
from datetime import datetime

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from app.extensions import db
from app.models.email_log import EmailLog
from app.utils.platform_settings import get_smtp_config


def _log_email(to_email, subject, status, error_message=None, organization_id=None,
                candidate_id=None, user_id=None, has_attachment=False):
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
            created_at=datetime.utcnow(),
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def send_otp_email(to_email: str, otp_code: str) -> None:
    """Send a password-reset OTP via SMTP (configured via the super-admin
    Integrations page, or .env as a fallback). Raises an exception if SMTP
    is not configured or sending fails, so the caller (forgot_password
    route) can show an appropriate error.

    Always uses platform-wide SMTP (no organization_id) - password reset
    happens before we know which organization's "brand" should be sending
    the email, and it's a platform-level auth flow either way."""

    smtp_host, smtp_port, smtp_username, smtp_password = get_smtp_config()

    subject = "Your Codevocado Password Reset OTP"
    body = (
        f"Your OTP for resetting your Codevocado password is: {otp_code}\n\n"
        f"This OTP is valid for 10 minutes. If you did not request this, please ignore this email."
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_username
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, [to_email], msg.as_string())
    except Exception as exc:
        _log_email(to_email, subject, status="failed", error_message=str(exc))
        raise
    else:
        _log_email(to_email, subject, status="sent")


def send_notification_email(
    to_email: str,
    subject: str,
    body: str,
    organization_id=None,
    html_body: str = None,
    attachments: list = None,
    candidate_id=None,
    user_id=None,
) -> None:
    """Send a notification email (e.g. candidate placement alerts, welcome
    emails). Raises an exception on failure - callers should wrap this in
    try/except so an email failure never breaks the main request flow.

    organization_id (optional, SRS FR-14): when given, uses that
    organization's own SMTP override if it has one configured, falling
    back to platform-wide settings otherwise - see get_smtp_config().

    html_body (optional): when given, sends a multipart email with both
    the plain-text `body` (fallback for clients that don't render HTML)
    and this HTML version (what most modern email clients will actually
    display). When omitted, sends plain text only.

    attachments (optional): list of dicts, each either
        {"path": "/absolute/path/to/file.pdf", "filename": "certificate.pdf"}
    or
        {"data": <bytes>, "filename": "certificate.pdf"}
    Use "path" when the file already exists on disk; use "data" when you
    have the bytes in memory already (e.g. straight from a PDF-generation
    function) and don't want to write a temp file first. "filename" is
    required in both cases - it's what the recipient sees.

    candidate_id / user_id (optional): who this email relates to, for the
    email_logs audit trail (see app/models/email_log.py).
    """

    smtp_host, smtp_port, smtp_username, smtp_password = get_smtp_config(organization_id)

    # Attachments (or an HTML alternative) require a multipart message.
    needs_multipart = html_body or attachments

    if needs_multipart:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = smtp_username
        msg["To"] = to_email

        # Text/HTML body goes in its own "alternative" sub-part so mail
        # clients pick whichever they can render, independent of attachments.
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(body, "plain"))
        if html_body:
            body_part.attach(MIMEText(html_body, "html"))
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
    else:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_username
        msg["To"] = to_email

    has_attachment = bool(attachments)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, [to_email], msg.as_string())
    except Exception as exc:
        _log_email(
            to_email, subject, status="failed", error_message=str(exc),
            organization_id=organization_id, candidate_id=candidate_id,
            user_id=user_id, has_attachment=has_attachment,
        )
        raise
    else:
        _log_email(
            to_email, subject, status="sent",
            organization_id=organization_id, candidate_id=candidate_id,
            user_id=user_id, has_attachment=has_attachment,
        )