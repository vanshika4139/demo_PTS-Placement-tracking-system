import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class RevokedToken(db.Model):
    """A refresh token that has been used (rotated) or revoked. Checked by /auth/refresh."""
    __tablename__ = "revoked_tokens"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    jti = Column(String(64), nullable=False, unique=True, index=True)
    token_type = Column(String(16), nullable=False, default="refresh")
    user_id = Column(MySQLCHAR(32), nullable=True, index=True)
    revoked_at = Column(DateTime, server_default=func.now(), nullable=False)
