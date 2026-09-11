from sqlalchemy import Column, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_code = Column(String(50), unique=True, nullable=False)
    organization_name = Column(String(200), nullable=False)
    registration_number = Column(String(100), nullable=True)
    gst_number = Column(String(50), nullable=True)
    pan_number = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    email = Column(String(150), nullable=True)
    mobile = Column(String(20), nullable=True)
    contact_person = Column(String(150), nullable=True)
    designation = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    country_id = Column(BigInteger, nullable=True)
    state_id = Column(BigInteger, nullable=True)  # see app/constants/indian_states.py for lookup
    district = Column(String(150), nullable=True)  # free text - no districts master table exists yet
    pincode = Column(String(10), nullable=True)
    logo = Column(String(500), nullable=True)
    subscription_plan_id = Column(MySQLCHAR(32), ForeignKey("plans.id"), nullable=True, index=True)
    billing_cycle = Column(String(20), nullable=True, default="monthly")  # monthly | quarterly | yearly
    subscription_expiry_date = Column(Date, nullable=True)
    storage_used = Column(BigInteger, nullable=True, default=0)
    candidate_limit = Column(Integer, nullable=True, default=0)
    whatsapp_credits = Column(Integer, nullable=True, default=0)
    sms_credits = Column(Integer, nullable=True, default=0)
    email_credits = Column(Integer, nullable=True, default=0)
    api_key = Column(String(255), nullable=True)
    webhook_url = Column(String(500), nullable=True)
    kyc_status = Column(String(30), nullable=True, default="PENDING")
    payment_status = Column(String(30), nullable=True, default="PENDING")
    status = Column(SmallInteger, nullable=False, default=1)  # 1 = Active, 0 = Suspended
    is_deleted = Column(Boolean, nullable=False, default=False)  # soft-delete, separate from suspend
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(BigInteger, nullable=True)
    modified_at = Column(DateTime, nullable=True)
    modified_by = Column(BigInteger, nullable=True)