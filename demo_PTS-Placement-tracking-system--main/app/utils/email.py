import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.utils.platform_settings import get_smtp_config


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

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, [to_email], msg.as_string())


def send_notification_email(to_email: str, subject: str, body: str, organization_id=None, html_body: str = None) -> None:
    """Send a notification email (e.g. candidate placement alerts, welcome
    emails). Raises an exception on failure - callers should wrap this in
    try/except so an email failure never breaks the main request flow.

    organization_id (optional, SRS FR-14): when given, uses that
    organization's own SMTP override if it has one configured, falling
    back to platform-wide settings otherwise - see get_smtp_config().

    html_body (optional): when given, sends a multipart email with both
    the plain-text `body` (fallback for clients that don't render HTML)
    and this HTML version (what most modern email clients will actually
    display). When omitted, sends plain text only - fully backward
    compatible with every existing caller of this function."""

    smtp_host, smtp_port, smtp_username, smtp_password = get_smtp_config(organization_id)

    if html_body:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_username
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_username
        msg["To"] = to_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, [to_email], msg.as_string())