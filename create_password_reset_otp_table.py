from wsgi import app
from app.extensions import db
from app.models import PasswordResetOTP

with app.app_context():
    db.create_all()
    print("Password reset OTP table created!")