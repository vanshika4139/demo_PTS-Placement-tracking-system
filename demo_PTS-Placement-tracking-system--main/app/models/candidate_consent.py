import uuid
from datetime import datetime

from app.extensions import db


class CandidateConsent(db.Model):
    """DPDP: one row each time a candidate accepts a privacy notice version.
    withdrawn_at is set when the candidate takes the consent back."""
    __tablename__ = "candidate_consents"

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    candidate_id = db.Column(db.String(32), nullable=False, index=True)
    organization_id = db.Column(db.BigInteger, nullable=True)
    notice_version = db.Column(db.String(20), nullable=False)
    consented_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(64), nullable=True)
    withdrawn_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)