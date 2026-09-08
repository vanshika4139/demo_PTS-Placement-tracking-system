"""
Seeds Permission rows (one per action, e.g. 'candidate.view'), custom Roles
(Organization Admin, Trainer, Recruiter, Viewer, Candidate Manager), and the
RolePermission mappings between them.

Super Admin does NOT need a role row - the User.is_super_admin flag already
grants full access everywhere (see app/utils/permissions.py).

Safe to re-run: skips anything that already exists.
"""

from wsgi import app
from app.extensions import db
from app.models import Permission, Role, RolePermission

PERMISSION_CODES = [
    ("dashboard.view", "View dashboard"),
    ("organization.view", "View organizations"),
    ("organization.create", "Create organizations"),
    ("organization.update", "Edit organizations"),
    ("candidate.view", "View candidates"),
    ("candidate.create", "Create candidates"),
    ("candidate.update", "Edit candidates"),
    ("candidate.delete", "Delete candidates"),
    ("candidate.import", "Bulk import candidates"),
    ("candidate.export", "Export candidates"),
    ("candidate.view_deleted", "View deleted candidates"),
    ("batch.view", "View batches"),
    ("batch.create", "Create batches"),
    ("batch.update", "Edit batches"),
    ("batch.delete", "Delete batches"),
    ("scheme.view", "View schemes"),
    ("scheme.create", "Create schemes"),
    ("scheme.update", "Edit schemes"),
    ("scheme.delete", "Delete schemes"),
    ("placement.view", "View placements"),
    ("placement.update", "Update placement / checkpoints"),
    ("tracking.view", "View follow-up tracking"),
    ("report.view", "View reports"),
    ("notification.view", "View notifications"),
    ("user.view", "View users"),
    ("user.create", "Create users"),
    ("user.update", "Edit users"),
    ("user.delete", "Delete users"),
    ("settings.view", "View/edit own settings"),
]

ROLES = {
    "organization_admin": {
        "name": "Organization Admin",
        "permissions": [
            "dashboard.view",
            "candidate.view", "candidate.create", "candidate.update", "candidate.delete",
            "candidate.import", "candidate.export", "candidate.view_deleted",
            "batch.view", "batch.create", "batch.update", "batch.delete",
            "scheme.view", "scheme.create", "scheme.update", "scheme.delete",
            "placement.view", "placement.update",
            "tracking.view", "report.view", "notification.view", "settings.view",
        ],
    },
    "trainer": {
        "name": "Trainer",
        "permissions": [
            "dashboard.view",
            "candidate.view", "candidate.create", "candidate.import",
            "batch.view", "scheme.view", "tracking.view",
            "notification.view", "settings.view",
        ],
    },
    "recruiter": {
        "name": "Recruiter",
        "permissions": [
            "dashboard.view",
            "candidate.view", "candidate.update",
            "placement.view", "placement.update",
            "tracking.view", "report.view", "notification.view", "settings.view",
        ],
    },
    "viewer": {
        "name": "Viewer",
        "permissions": [
            "dashboard.view",
            "candidate.view", "batch.view", "scheme.view", "placement.view",
            "tracking.view", "report.view", "notification.view", "settings.view",
        ],
    },
    "candidate_manager": {
        "name": "Candidate Manager",
        "permissions": [
            "dashboard.view",
            "candidate.view", "candidate.create", "candidate.update", "candidate.delete",
            "candidate.import", "candidate.export", "candidate.view_deleted",
            "notification.view", "settings.view",
        ],
    },
}


def seed():
    perm_created, perm_skipped = 0, 0
    code_to_permission = {}
    for code, description in PERMISSION_CODES:
        existing = Permission.query.filter_by(code=code).first()
        if existing:
            code_to_permission[code] = existing
            perm_skipped += 1
            continue
        perm = Permission(code=code, description=description)
        db.session.add(perm)
        db.session.flush()
        code_to_permission[code] = perm
        perm_created += 1

    role_created, role_skipped = 0, 0
    code_to_role = {}
    for role_code, role_data in ROLES.items():
        existing = Role.query.filter_by(code=role_code).first()
        if existing:
            code_to_role[role_code] = existing
            role_skipped += 1
            continue
        role = Role(name=role_data["name"], code=role_code)
        db.session.add(role)
        db.session.flush()
        code_to_role[role_code] = role
        role_created += 1

    db.session.commit()

    mapping_created, mapping_skipped = 0, 0
    for role_code, role_data in ROLES.items():
        role = code_to_role[role_code]
        for perm_code in role_data["permissions"]:
            permission = code_to_permission.get(perm_code)
            if not permission:
                continue
            existing = RolePermission.query.filter_by(role_id=role.id, permission_id=permission.id).first()
            if existing:
                mapping_skipped += 1
                continue
            db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
            mapping_created += 1

    db.session.commit()

    print(f"Permissions created: {perm_created}, skipped: {perm_skipped}")
    print(f"Roles created: {role_created}, skipped: {role_skipped}")
    print(f"Role-permission mappings created: {mapping_created}, skipped: {mapping_skipped}")


if __name__ == "__main__":
    with app.app_context():
        seed()