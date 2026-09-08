from wsgi import app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    user = User.query.filter_by(email="vanshika3@gmail.com").first()
    if user:
        user.password_hash = generate_password_hash("Test@123")
        db.session.commit()
        print("Password updated successfully for", user.email)
    else:
        print("User not found")