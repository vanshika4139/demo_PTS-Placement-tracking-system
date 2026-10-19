import uuid
from datetime import datetime

from app.extensions import db


class DataBreach(db.Model):
    """DPDP: record of a personal data breach and the notice sent to affected candidates."""
    __tablename__ = "data_breaches"

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    organization_id = db.Column(db.BigInteger, nullable=True)  # None = all organizations
    title = db.Column(db.String(200), nullable=False)
    occurred = db.Column(db.String(120), nullable=True)
    data_involved = db.Column(db.Text, nullable=True)
    what_happened = db.Column(db.Text, nullable=True)
    consequences = db.Column(db.Text, nullable=True)
    measures = db.Column(db.Text, nullable=True)
    advice = db.Column(db.Text, nullable=True)
    contact = db.Column(db.String(255), nullable=True)
    board_reported = db.Column(db.Boolean, nullable=False, default=False)
    recipients_total = db.Column(db.Integer, nullable=False, default=0)
    recipients_failed = db.Column(db.Integer, nullable=False, default=0)
    notified_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(32), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)