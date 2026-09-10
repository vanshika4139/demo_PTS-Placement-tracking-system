import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Plan(db.Model):
    """A subscription plan (Starter / Professional / Enterprise / Government)
    that an organization can be assigned to. Platform-wide - not scoped to
    an organization_id, same as Module.

    Organization.subscription_plan_id already exists as a bare BigInteger
    FK-by-convention (no actual ForeignKey constraint was ever added on that
    column), so Plan.id is intentionally left as the same MySQLCHAR(32) id
    style used everywhere else in this codebase, and organization.py's
    subscription_plan_id will need to change from BigInteger to
    MySQLCHAR(32) to actually reference it - see migration notes.
    """

    __tablename__ = "plans"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    name = Column(String(120), nullable=False)
    code = Column(String(50), unique=True, nullable=False)  # e.g. "starter", "professional"
    price = Column(Numeric(10, 2), nullable=False, default=0)
    default_billing_cycle = Column(String(20), nullable=False, default="monthly")  # monthly | quarterly | yearly

    candidate_limit = Column(Integer, nullable=False, default=0)
    whatsapp_credits = Column(Integer, nullable=False, default=0)
    sms_credits = Column(Integer, nullable=False, default=0)
    email_credits = Column(Integer, nullable=False, default=0)
    storage_limit_mb = Column(Integer, nullable=True)
    api_access = Column(Boolean, nullable=False, default=False)
    custom_branding = Column(Boolean, nullable=False, default=False)
    report_access_level = Column(String(30), nullable=False, default="basic")  # basic | advanced | full

    display_order = Column(Integer, nullable=False, default=0)
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = Inactive (retired plan)

    created_by = Column(MySQLCHAR(32), nullable=True)
    modified_by = Column(MySQLCHAR(32), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)