from wsgi import app
from app.extensions import db
from app.models import ActivityLog

with app.app_context():
    db.create_all()
    print("Activity log table created!")