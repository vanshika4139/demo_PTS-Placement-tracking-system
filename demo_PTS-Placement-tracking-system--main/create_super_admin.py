from werkzeug.security import generate_password_hash
import os
PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD")
EMAIL = os.environ.get("SUPER_ADMIN_EMAIL")
if not EMAIL:
    raise SystemExit("Set SUPER_ADMIN_EMAIL env var first")
if not PASSWORD:
    raise SystemExit("Set SUPER_ADMIN_PASSWORD env var first")
from wsgi import app
from app.extensions import db
from app.models import User

with app.app_context():
    existing = User.query.filter_by(email=EMAIL).first()
    if existing:
        print("Already exists:", existing.email)
    else:
        admin = User(
            email=EMAIL,
            password_hash=generate_password_hash(PASSWORD),
            full_name="Super Admin",
            is_super_admin=True,
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()
        print("Super admin created:", admin.email, "(password from SUPER_ADMIN_PASSWORD)")