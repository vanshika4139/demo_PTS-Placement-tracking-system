from wsgi import app
from app.extensions import db
from app.models import Invoice  # noqa: F401 - import registers the model with SQLAlchemy metadata

with app.app_context():
    db.create_all()
    print("Invoices table created (or already existed).")