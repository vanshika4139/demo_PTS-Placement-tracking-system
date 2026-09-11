from sqlalchemy import text

from wsgi import app
from app.extensions import db

with app.app_context():
    print("--- payment_gateway columns on platform_settings ---")
    rows = db.session.execute(
        text("SHOW COLUMNS FROM platform_settings LIKE 'payment_gateway%'")
    ).fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]}  ({row[1]})")
    else:
        print("  None found!")

    print("\n--- invoices table ---")
    rows = db.session.execute(text("SHOW TABLES LIKE 'invoices'")).fetchall()
    if rows:
        print("  invoices table exists.")
    else:
        print("  invoices table NOT found!")