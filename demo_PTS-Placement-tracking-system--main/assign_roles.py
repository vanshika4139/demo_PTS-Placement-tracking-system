"""
Assigns the 'organization_admin' role to every existing non-super-admin,
non-deleted user who doesn't already have a role assigned.

This keeps existing users' access unchanged before permission checks are
enforced on any routes - it just gives them the role that matches what
they can already do today.

Safe to re-run.
"""

from wsgi import app
from app.extensions import db
from app.models import Role, User, UserRole


def run():
    org_admin_role = Role.query.filter_by(code="organization_admin").first()
    if not org_admin_role:
        print("ERROR: 'organization_admin' role not found. Run seed_rbac.py first.")
        return

    users = User.query.filter_by(is_deleted=False, is_super_admin=False).all()

    assigned = 0
    already_had_role = 0

    for user in users:
        existing = UserRole.query.filter_by(user_id=user.id, is_deleted=False).first()
        if existing:
            already_had_role += 1
            continue
        db.session.add(UserRole(user_id=user.id, role_id=org_admin_role.id))
        assigned += 1
        print(f"  Assigned 'Organization Admin' role to: {user.full_name} ({user.email})")

    db.session.commit()
    print(f"\nRole assigned to {assigned} user(s). {already_had_role} already had a role.")


if __name__ == "__main__":
    with app.app_context():
        run()