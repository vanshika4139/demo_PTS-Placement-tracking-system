"""
Seeds the module / sub_module tables with the menu structure that matches
the Placement Tracking System's actual current routes.

Safe to re-run: skips modules/sub-modules that already exist (matched by name / permission_key).
"""

from wsgi import app
from app.extensions import db
from app.models import Module, SubModule

MENU_STRUCTURE = [
    {
        "name": "Dashboard",
        "order_no": 1,
        "icon_image": "dashboard",
        "sub_modules": [
            {"name": "Dashboard", "sub_url": "/organization/dashboard", "permission_key": "dashboard.view", "order_no": 1},
        ],
    },
    {
        "name": "Organization Management",
        "order_no": 2,
        "icon_image": "building",
        "sub_modules": [
            {"name": "Organization List", "sub_url": "/super-admin/organizations", "permission_key": "organization.view", "order_no": 1},
            {"name": "Add Organization", "sub_url": "/super-admin/organizations/create", "permission_key": "organization.create", "order_no": 2},
        ],
    },
    {
        "name": "Candidate Management",
        "order_no": 3,
        "icon_image": "users",
        "sub_modules": [
            {"name": "Candidate List", "sub_url": "/organization/candidates", "permission_key": "candidate.view", "order_no": 1},
            {"name": "Add Candidate", "sub_url": "/organization/candidates/create", "permission_key": "candidate.create", "order_no": 2},
            {"name": "Import Candidates", "sub_url": "/candidates/import", "permission_key": "candidate.import", "order_no": 3},
            {"name": "Deleted Candidates", "sub_url": "/organization/candidates/deleted", "permission_key": "candidate.view_deleted", "order_no": 4},
            {"name": "Export Candidates", "sub_url": "/organization/candidates/export.xlsx", "permission_key": "candidate.export", "order_no": 5},
        ],
    },
    {
        "name": "Batches",
        "order_no": 4,
        "icon_image": "layers",
        "sub_modules": [
            {"name": "Batch List", "sub_url": "/organization/batches", "permission_key": "batch.view", "order_no": 1},
            {"name": "Add Batch", "sub_url": "/organization/batches/create", "permission_key": "batch.create", "order_no": 2},
        ],
    },
    {
        "name": "Schemes",
        "order_no": 5,
        "icon_image": "clipboard",
        "sub_modules": [
            {"name": "Scheme List", "sub_url": "/organization/schemes", "permission_key": "scheme.view", "order_no": 1},
            {"name": "Add Scheme", "sub_url": "/organization/schemes/create", "permission_key": "scheme.create", "order_no": 2},
        ],
    },
    {
        "name": "Placement",
        "order_no": 6,
        "icon_image": "briefcase",
        "sub_modules": [
            {"name": "Placement List", "sub_url": "/organization/placements", "permission_key": "placement.view", "order_no": 1},
        ],
    },
    {
        "name": "Tracking",
        "order_no": 7,
        "icon_image": "activity",
        "sub_modules": [
            {"name": "Follow-up Tracking", "sub_url": "/organization/tracking", "permission_key": "tracking.view", "order_no": 1},
        ],
    },
    {
        "name": "Reports",
        "order_no": 8,
        "icon_image": "bar-chart",
        "sub_modules": [
            {"name": "Reports", "sub_url": "/reports", "permission_key": "report.view", "order_no": 1},
        ],
    },
    {
        "name": "Notifications",
        "order_no": 9,
        "icon_image": "bell",
        "sub_modules": [
            {"name": "Notifications", "sub_url": "/notifications", "permission_key": "notification.view", "order_no": 1},
        ],
    },
    {
        "name": "User Management",
        "order_no": 10,
        "icon_image": "user-cog",
        "sub_modules": [
            {"name": "User List", "sub_url": "/super-admin/users", "permission_key": "user.view", "order_no": 1},
            {"name": "Add User", "sub_url": "/super-admin/users/create", "permission_key": "user.create", "order_no": 2},
        ],
    },
    {
        "name": "Settings",
        "order_no": 11,
        "icon_image": "settings",
        "sub_modules": [
            {"name": "Settings", "sub_url": "/settings/profile", "permission_key": "settings.view", "order_no": 1},
        ],
    },
]


def seed():
    created_modules = 0
    created_sub_modules = 0
    skipped_modules = 0
    skipped_sub_modules = 0

    for module_data in MENU_STRUCTURE:
        module = Module.query.filter_by(name=module_data["name"]).first()
        if module:
            skipped_modules += 1
        else:
            module = Module(
                name=module_data["name"],
                order_no=module_data["order_no"],
                icon_image=module_data.get("icon_image"),
                status=1,
            )
            db.session.add(module)
            db.session.flush()  # get module.id before committing
            created_modules += 1

        for sm_data in module_data["sub_modules"]:
            existing = SubModule.query.filter_by(permission_key=sm_data["permission_key"]).first()
            if existing:
                skipped_sub_modules += 1
                continue
            sub_module = SubModule(
                module_id=module.id,
                name=sm_data["name"],
                sub_url=sm_data["sub_url"],
                permission_key=sm_data["permission_key"],
                sub_module_order_no=sm_data["order_no"],
                status=1,
            )
            db.session.add(sub_module)
            created_sub_modules += 1

    db.session.commit()

    print(f"Modules created: {created_modules}, skipped (already existed): {skipped_modules}")
    print(f"Sub-modules created: {created_sub_modules}, skipped (already existed): {skipped_sub_modules}")


if __name__ == "__main__":
    with app.app_context():
        seed()