from wsgi import app
from app.extensions import db
from app.models import UserPermissionOverride

with app.app_context():
    db.create_all()
    print("User permission override table created!")