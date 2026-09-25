import uuid
from datetime import datetime

from app.extensions import db


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