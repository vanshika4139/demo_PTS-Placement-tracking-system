import smtplib
from email.mime.text import MIMEText

from app.utils.platform_settings import get_smtp_config


def send_otp_email(to_email: str, otp_code: str) -> None:
    """Send a password-reset OTP via SMTP (configured via the super-admin
    Integrations page, or .env as a fallback). Raises an exception if SMTP
    is not configured or sending fails, so the caller (forgot_password
    route) can show an appropriate error."""

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


def send_notification_email(to_email: str, subject: str, body: str) -> None:
    """Send a plain-text notification email (e.g. candidate placement alerts).
    Raises an exception on failure - callers should wrap this in try/except
    so an email failure never breaks the main request flow."""

    smtp_host, smtp_port, smtp_username, smtp_password = get_smtp_config()

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_username
    msg["To"] = to_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, [to_email], msg.as_string())