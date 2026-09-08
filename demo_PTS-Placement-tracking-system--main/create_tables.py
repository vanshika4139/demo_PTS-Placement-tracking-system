from wsgi import app
from app.extensions import db
from app.models import User, Role, Permission, RolePermission, UserRole, Candidate, Organization

with app.app_context():
    db.create_all()
    print("All tables created successfully!")