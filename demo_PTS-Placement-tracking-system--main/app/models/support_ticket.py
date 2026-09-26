# =============================================================================
# NEW FILE: app/models/support_ticket.py
#
# After creating this file, add ONE line to app/models/__init__.py so the
# model is registered/importable the same way other models are, e.g.:
#     from app.models.support_ticket import SupportTicket
# (Look at how "EmailLog" is imported there and copy the same pattern.)
# =============================================================================

import uuid
from datetime import datetime

from app.extensions import db


class SupportTicket(db.Model):
    __tablename__ = "support_tickets"

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)

    subject = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)

    # "open" -> just submitted, nobody has looked at it yet
    # "in_progress" -> a super admin is working on it
    # "resolved" -> closed
    status = db.Column(db.String(20), nullable=False, default="open")

    # Who raised it - kept as plain text fields (not just a foreign key)
    # so the ticket still shows a name/email even if that user account is
    # later deleted or deactivated.
    reporter_name = db.Column(db.String(255))
    reporter_email = db.Column(db.String(255))
    organization_id = db.Column(db.String(32), nullable=True)
    user_id = db.Column(db.String(32), nullable=True)

    # Filled in by the super admin when they respond
    admin_reply = db.Column(db.Text, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)