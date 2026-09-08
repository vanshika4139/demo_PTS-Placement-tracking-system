import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class PasswordResetOTP(db.Model):
    __tablename__ = "password_reset_otps"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def is_valid(self):
        """OTP is valid if it hasn't been used yet and hasn't expired."""
        return (not self.is_used) and (datetime.utcnow() <= self.expires_at)
