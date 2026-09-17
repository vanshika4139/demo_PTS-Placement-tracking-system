import uuid

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class UserSession(db.Model):
    """One row per active login, so a super admin can see who is logged in
    from where and force-logout a specific session. session_token is a
    random value stored in the Flask session cookie AND here - the
    login_required decorator checks this row is_active on every request,
    so a force-logout takes effect on the user's very next request rather
    than waiting for the cookie to expire naturally.
    """

    __tablename__ = "user_sessions"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    session_token = Column(MySQLCHAR(32), nullable=False, unique=True, index=True)
    user_id = Column(MySQLCHAR(32), nullable=False, index=True)
    user_email = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_active_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
