from wsgi import app
from app.extensions import db
from app.models import PlatformSettings

with app.app_context():
    db.create_all()

    existing = PlatformSettings.query.get("platform")
    if not existing:
        db.session.add(PlatformSettings(id="platform"))
        db.session.commit()
        print("Platform settings table created and seeded with a default row!")
    else:
        print("Platform settings table already exists with its row.")