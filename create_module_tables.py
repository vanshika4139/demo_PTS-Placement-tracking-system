from wsgi import app
from app.extensions import db
from app.models import Module, SubModule

with app.app_context():
    db.create_all()
    print("Module and Sub-Module tables created!")