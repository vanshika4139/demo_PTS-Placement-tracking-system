import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class KycDocument(db.Model):
    """One uploaded KYC document belonging to an organization.

    SRS FR-06 asks for per-document approval status (Pending / Approved /
    Rejected), which the single Organization.kyc_status column can't
    represent on its own - that column now tracks the organization's
    OVERALL kyc state (derived from these rows; see
    app/services/kyc.py:recompute_organization_kyc_status), while this
    table tracks each individual document.
    """

    __tablename__ = "kyc_documents"

    DOC_TYPES = (
        "PAN",
        "GST_CERTIFICATE",
        "REGISTRATION_CERTIFICATE",
        "BANK_DETAILS",
        "AADHAAR",
    )
    STATUSES = ("PENDING", "APPROVED", "REJECTED")

    # Human-readable labels for DOC_TYPES, used by the Super Admin KYC
    # Documents page so the UI doesn't have to hardcode/duplicate this list.
    DOC_TYPE_LABELS = {
        "PAN": "PAN Card",
        "GST_CERTIFICATE": "GST Certificate",
        "REGISTRATION_CERTIFICATE": "Registration Certificate",
        "BANK_DETAILS": "Bank Details / Cancelled Cheque",
        "AADHAAR": "Aadhaar Card",
    }

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False)  # one of DOC_TYPES
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")  # one of STATUSES
    remarks = Column(Text, nullable=True)  # required when status == REJECTED

    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    # Matches users.id, which is a UUID CHAR(32) in this app (same pattern
    # as KycDocument.id / Plan.id above) - NOT a BigInteger. Was originally
    # written as BigInteger which fails with "Incorrect integer value" the
    # moment a real session user (UUID id) uploads/reviews a document.
    uploaded_by = Column(MySQLCHAR(32), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(MySQLCHAR(32), nullable=True)