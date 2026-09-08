from wsgi import app
from app.extensions import db
from app.models import UserSettings

with app.app_context():
    db.create_all()
    print("User settings table created!")