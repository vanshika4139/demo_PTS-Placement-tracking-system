from werkzeug.security import generate_password_hash
from wsgi import app
from app.extensions import db
from app.models import User

with app.app_context():
    existing = User.query.filter_by(email="admin@codevocado.com").first()
    if existing:
        print("Already exists:", existing.email)
    else:
        admin = User(
            email="admin@codevocado.com",
            password_hash=generate_password_hash("Admin@123"),
            full_name="Super Admin",
            is_super_admin=True,
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()
        print("Super admin created:", admin.email, "| password: Admin@123")