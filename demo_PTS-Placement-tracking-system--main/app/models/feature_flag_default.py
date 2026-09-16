from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class FeatureFlagDefault(db.Model):
    """Super-admin-controlled override of a feature's default_enabled value
    (see app/utils/feature_flags.py AVAILABLE_FEATURES). A row here means
    "the admin changed this from the UI" - absence of a row means the
    hardcoded default in AVAILABLE_FEATURES still applies. This is checked
    BEFORE the hardcoded default but AFTER any per-organization override,
    so an organization-specific override always wins regardless of the
    global default.
    """

    __tablename__ = "feature_flag_defaults"

    feature_key = Column(String(100), primary_key=True)
    is_enabled = Column(Boolean, nullable=False)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
