"""
Creates 3 test users (Trainer, Recruiter, Viewer) under the first available
organization, and assigns them their matching RBAC role.

All test users get the password: Test@123

Safe to re-run: skips users that already exist.
"""

from werkzeug.security import generate_password_hash

from wsgi import app
from app.extensions import db
from app.models import Organization, Role, User, UserRole

TEST_USERS = [
    {
        "email": "trainer.test@codevocado.com",
        "full_name": "Trainer Test",
        "username": "trainer_test",
        "role_code": "trainer",
    },
    {
        "email": "recruiter.test@codevocado.com",
        "full_name": "Recruiter Test",
        "username": "recruiter_test",
        "role_code": "recruiter",
    },
    {
        "email": "viewer.test@codevocado.com",
        "full_name": "Viewer Test",
        "username": "viewer_test",
        "role_code": "viewer",
    },
]

PASSWORD = "Test@123"


def run():
    organization = Organization.query.filter_by(status=1).first()
    if not organization:
        print("ERROR: No active organization found. Create one first.")
        return

    for entry in TEST_USERS:
        existing_user = User.query.filter_by(email=entry["email"]).first()
        if existing_user:
            print(f"Skipped (already exists): {entry['email']}")
            continue

        role = Role.query.filter_by(code=entry["role_code"]).first()
        if not role:
            print(f"ERROR: Role '{entry['role_code']}' not found. Run seed_rbac.py first.")
            continue

        user = User(
            email=entry["email"],
            full_name=entry["full_name"],
            username=entry["username"],
            password_hash=generate_password_hash(PASSWORD),
            organization_id=organization.id,
            is_super_admin=False,
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()

        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()

        print(f"Created: {entry['email']} (role: {role.name}, org: {organization.organization_name})")

    print(f"\nAll test users use the password: {PASSWORD}")


if __name__ == "__main__":
    with app.app_context():
        run()