"""Organization-scoped API access via API key (X-API-Key header), for
external scripts/dashboards - see app/utils/api_keys.py for how keys are
generated and verified. This is separate from the JWT-based session auth
in app/api/v1/auth.py, which is for the web app itself.
"""

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Candidate, Organization
from app.utils.api_keys import verify_api_key

bp = Blueprint("api_v1_organizations", __name__)


def _authenticate_by_api_key():
    """Returns the Organization matching the X-API-Key header, or None if
    missing/invalid. Checks every organization with a key set - fine at
    this scale (a handful of orgs), and avoids needing a lookup table
    since the key itself is only ever stored hashed."""
    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key:
        return None

    for org in Organization.query.filter(Organization.api_key.isnot(None)).all():
        if verify_api_key(api_key, org.api_key):
            return org
    return None


@bp.route("/organizations/me/stats")
def my_organization_stats():
    """Returns this organization's candidate stats. Requires a valid
    X-API-Key header - see Super Admin > Organization detail page to
    generate one."""
    org = _authenticate_by_api_key()
    if not org:
        return jsonify({"error": "Invalid or missing API key"}), 401

    candidates = Candidate.query.filter_by(organization_id=org.id, is_deleted=False).all()
    total = len(candidates)
    placed = sum(1 for c in candidates if c.employer_name)

    return jsonify({
        "organization": org.organization_name,
        "total_candidates": total,
        "placed": placed,
        "placement_rate": round((placed / total * 100), 1) if total else 0,
    })
