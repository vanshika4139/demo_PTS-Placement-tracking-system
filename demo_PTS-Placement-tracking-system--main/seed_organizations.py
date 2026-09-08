from dotenv import load_dotenv
load_dotenv()

from wsgi import app
from app.extensions import db
from app.models import Organization

with app.app_context():
    orgs_data = [
        {
            "organization_code": "ORG001",
            "organization_name": "Tech Mahindra Foundation",
            "registration_number": "REG2026001",
            "gst_number": "27ABCDE1234F1Z5",
            "pan_number": "ABCDE1234F",
            "contact_person": "Rahul Sharma",
            "email": "hr@techmahindra.com",
            "mobile": "9876543210",
            "address": "Sector 62, Noida, UP",
        },
        {
            "organization_code": "ORG002",
            "organization_name": "Infosys BPM",
            "registration_number": "REG2026002",
            "gst_number": "29ABCDE5678F1Z5",
            "pan_number": "ABCDE5678F",
            "contact_person": "Priya Nair",
            "email": "hr@infosysbpm.com",
            "mobile": "9123456780",
            "address": "Electronic City, Bangalore",
        },
        {
            "organization_code": "ORG003",
            "organization_name": "Wipro Skilling",
            "registration_number": "REG2026003",
            "gst_number": "36ABCDE9012F1Z5",
            "pan_number": "ABCDE9012F",
            "contact_person": "Amit Verma",
            "email": "hr@wiproskilling.com",
            "mobile": "9988776655",
            "address": "Hitech City, Hyderabad",
        },
        {
            "organization_code": "ORG004",
            "organization_name": "Capgemini Learning",
            "registration_number": "REG2026004",
            "gst_number": "07ABCDE3456F1Z5",
            "pan_number": "ABCDE3456F",
            "contact_person": "Sneha Iyer",
            "email": "hr@capgeminilearning.com",
            "mobile": "9871234560",
            "address": "DLF Cyber City, Gurugram",
        },
    ]

    for data in orgs_data:
        existing = Organization.query.filter_by(organization_code=data["organization_code"]).first()
        if existing:
            print(f"Skipped (already exists): {data['organization_code']}")
            continue
        org = Organization(
            status=1,
            kyc_status="PENDING",
            payment_status="PENDING",
            candidate_limit=0,
            storage_used=0,
            whatsapp_credits=0,
            sms_credits=0,
            email_credits=0,
            **data,
        )
        db.session.add(org)

    db.session.commit()
    print("Organizations seeded successfully!")