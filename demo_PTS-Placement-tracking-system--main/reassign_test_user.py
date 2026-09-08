"""
Reassigns vanshika3@gmail.com from 'Organization Admin' to the new
'Candidate Manager' role (candidate-only access, no batches/schemes/
organizations/users access).

Run seed_rbac.py FIRST (to create the candidate_manager role), then run this.
"""

from wsgi import app
from app.extensions import db
from app.models import Role, User, UserRole

TARGET_EMAIL = "vanshika3@gmail.com"
NEW_ROLE_CODE = "candidate_manager"


def run():
    user = User.query.filter_by(email=TARGET_EMAIL, is_deleted=False).first()
    if not user:
        print(f"ERROR: No user found with email {TARGET_EMAIL}")
        return

    new_role = Role.query.filter_by(code=NEW_ROLE_CODE).first()
    if not new_role:
        print(f"ERROR: Role '{NEW_ROLE_CODE}' not found. Run seed_rbac.py first.")
        return

    old_assignments = UserRole.query.filter_by(user_id=user.id, is_deleted=False).all()
    for assignment in old_assignments:
        db.session.delete(assignment)

    db.session.add(UserRole(user_id=user.id, role_id=new_role.id))
    db.session.commit()

    print(f"{user.full_name} ({user.email}) is now a 'Candidate Manager'.")
    print("Removed previous role assignment(s), if any.")


if __name__ == "__main__":
    with app.app_context():
        run()
