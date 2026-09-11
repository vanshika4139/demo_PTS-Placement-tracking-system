"""Keeps Organization.kyc_status in sync with its individual KycDocument
rows (SRS FR-06/FR-07).

Rule:
    - Any document REJECTED               -> organization kyc_status = REJECTED
    - All required doc types APPROVED     -> organization kyc_status = APPROVED
    - Anything else (missing docs, some
      still PENDING)                      -> organization kyc_status = PENDING

Call recompute_organization_kyc_status(organization_id) after every
document upload, approval, or rejection so the org-level status shown
everywhere else (Organizations list, dashboard filters, login gate)
stays correct without every call site re-implementing this logic.
"""
from app.extensions import db
from app.models import KycDocument, Organization

REQUIRED_DOC_TYPES = set(KycDocument.DOC_TYPES)


def recompute_organization_kyc_status(organization_id):
    organization = Organization.query.get(organization_id)
    if not organization:
        return None

    documents = KycDocument.query.filter_by(organization_id=organization_id).all()

    if any(doc.status == "REJECTED" for doc in documents):
        new_status = "REJECTED"
    else:
        uploaded_types = {doc.doc_type for doc in documents}
        all_required_present = REQUIRED_DOC_TYPES.issubset(uploaded_types)
        all_approved = all_required_present and all(doc.status == "APPROVED" for doc in documents)
        new_status = "APPROVED" if all_approved else "PENDING"

    if organization.kyc_status != new_status:
        organization.kyc_status = new_status
        db.session.commit()

    return new_status