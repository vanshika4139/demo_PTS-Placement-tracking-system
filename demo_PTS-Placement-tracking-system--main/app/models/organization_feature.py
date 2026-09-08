import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class OrganizationFeature(db.Model):
    """A per-organization override for a named feature flag.

    Absence of a row for (organization_id, feature_key) means "use the
    default" - see app/utils/feature_flags.py AVAILABLE_FEATURES for each
    feature's default_enabled value. A row only needs to exist when an
    organization's setting differs from the default.
    """

    __tablename__ = "organization_features"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False, index=True)
    feature_key = Column(String(100), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "feature_key", name="uq_org_feature"),
    )