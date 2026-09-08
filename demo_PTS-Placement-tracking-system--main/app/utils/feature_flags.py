"""
Per-organization feature flags.

Each entry in AVAILABLE_FEATURES is a togglable capability. An organization
uses the default_enabled value unless a row exists for it in
organization_features - so turning a feature ON for everyone just means
raising the default here, no data migration needed.

Usage in routes:

    from app.utils.feature_flags import is_feature_enabled

    if not is_feature_enabled(organization_id, "candidate_import"):
        flash("Bulk import is not enabled for your organization.", "error")
        return redirect(url_for("frontend.organization_candidates"))
"""

from app.extensions import db
from app.models import OrganizationFeature

AVAILABLE_FEATURES = {
    "candidate_import": {
        "label": "Bulk Candidate Import",
        "description": "Allow CSV bulk import of candidates.",
        "default_enabled": True,
    },
    "candidate_export": {
        "label": "Excel / PDF Export",
        "description": "Allow exporting candidates to Excel and PDF.",
        "default_enabled": True,
    },
    "candidate_feedback": {
        "label": "Post-Placement Feedback",
        "description": "Placed candidates can submit a placement feedback rating.",
        "default_enabled": True,
    },
    "multi_language_portal": {
        "label": "Multi-language Candidate Portal",
        "description": "English/Hindi language switch on the candidate portal.",
        "default_enabled": True,
    },
    "whatsapp_notifications": {
        "label": "WhatsApp Notifications",
        "description": "Send WhatsApp notifications to candidates (consumes WhatsApp credits).",
        "default_enabled": False,
    },
}


def get_organization_feature_map(organization_id):
    """Returns {feature_key: is_enabled} for every known feature, applying
    the organization's overrides on top of each feature's default."""
    result = {key: cfg["default_enabled"] for key, cfg in AVAILABLE_FEATURES.items()}

    overrides = OrganizationFeature.query.filter_by(organization_id=organization_id).all()
    for row in overrides:
        if row.feature_key in result:
            result[row.feature_key] = row.is_enabled

    return result


def is_feature_enabled(organization_id, feature_key):
    """Single-flag check for use inside a route/decorator. Super admin
    routes that act across all organizations should not call this - it's
    for organization-scoped actions only."""
    if feature_key not in AVAILABLE_FEATURES:
        return True  # unknown key - fail open rather than silently blocking something

    if not organization_id:
        return AVAILABLE_FEATURES[feature_key]["default_enabled"]

    override = OrganizationFeature.query.filter_by(
        organization_id=organization_id, feature_key=feature_key
    ).first()
    if override is not None:
        return override.is_enabled

    return AVAILABLE_FEATURES[feature_key]["default_enabled"]


def set_organization_feature(organization_id, feature_key, is_enabled, actor_id=None):
    """Create or update the override row for one organization/feature pair."""
    if feature_key not in AVAILABLE_FEATURES:
        return False

    row = OrganizationFeature.query.filter_by(
        organization_id=organization_id, feature_key=feature_key
    ).first()

    if row is None:
        row = OrganizationFeature(
            organization_id=organization_id,
            feature_key=feature_key,
            is_enabled=is_enabled,
            created_by=actor_id,
            modified_by=actor_id,
        )
        db.session.add(row)
    else:
        row.is_enabled = is_enabled
        row.modified_by = actor_id

    db.session.commit()
    return True