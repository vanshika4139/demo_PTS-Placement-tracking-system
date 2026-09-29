import re
import uuid
from datetime import datetime

from app.extensions import db


# Email types shown in Email Logs. Order matters: classify_email_type() checks
# rules top to bottom. The list is (key, label) - keys are stored in the DB.
EMAIL_TYPES = [
    ("support_ticket_raised", "Support Ticket Raised"),
    ("support_ticket_reply", "Support Ticket Reply"),
    ("otp", "Password Reset OTP"),
    ("welcome", "Welcome"),
    ("placement", "Placement"),
    ("salary", "Salary Update"),
    ("verification", "Verification Request"),
    ("certificate", "Certificate"),
    ("security", "Security Alert"),
    ("subscription", "Subscription / Billing"),
    ("other", "Other"),
]
EMAIL_TYPE_LABELS = dict(EMAIL_TYPES)


def classify_email_type(subject):
    """Works out the email type from the subject line."""
    s = (subject or "").strip().lower()
    if s.startswith("new support ticket"):
        return "support_ticket_raised"
    if s.startswith("re:"):
        return "support_ticket_reply"
    if "password reset" in s or re.search(r"\botp\b", s):
        return "otp"
    if s.startswith("welcome"):
        return "welcome"
    if "salary" in s:
        return "salary"
    if "verification" in s:
        return "verification"
    if "certificate" in s:
        return "certificate"
    if "email address was" in s or "password was" in s or "security" in s:
        return "security"
    if "subscription" in s or "invoice" in s or "payment" in s:
        return "subscription"
    if "placement" in s or "placed" in s or "congratulations" in s:
        return "placement"
    return "other"


class EmailLog(db.Model):
    __tablename__ = "email_logs"

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    to_email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False)  # "sent" | "failed"
    error_message = db.Column(db.Text)

    organization_id = db.Column(db.String(32), nullable=True)
    candidate_id = db.Column(db.String(32), nullable=True)
    user_id = db.Column(db.String(32), nullable=True)

    has_attachment = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    email_type = db.Column(db.String(40), nullable=True, index=True)

    @property
    def email_type_label(self):
        key = self.email_type or classify_email_type(self.subject)
        return EMAIL_TYPE_LABELS.get(key, "Other")
