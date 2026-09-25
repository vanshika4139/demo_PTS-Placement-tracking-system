"""
One-time rename: aligns existing role display names with SRS FR-12 naming.
Only updates Role.name - Role.code and Role.id stay the same, so nothing
else (permissions, user assignments) is affected.
"""
from wsgi import app
from app.extensions import db
from app.models import Role

RENAMES = {
    "recruiter": "Placement Officer",
    "viewer": "Call Center Executive",
    "candidate_manager": "HR",
}

def run():
    updated = 0
    for code, new_name in RENAMES.items():
        role = Role.query.filter_by(code=code).first()
        if not role:
            print(f"skip: no role with code={code}")
            continue
        old_name = role.name
        role.name = new_name
        updated += 1
        print(f"renamed: {old_name} -> {new_name} (code={code})")
    db.session.commit()
    print(f"Done. {updated} role(s) renamed.")

if __name__ == "__main__":
    with app.app_context():
        run()