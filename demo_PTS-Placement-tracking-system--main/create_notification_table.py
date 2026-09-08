from wsgi import app
from app.extensions import db
from app.models import Notification

with app.app_context():
    db.create_all()
    print("Notification table created!")