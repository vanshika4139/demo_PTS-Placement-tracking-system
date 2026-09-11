"""
platform_settings already exists in the database, so db.create_all() won't
add the new payment_gateway_* columns to it - create_all() only creates
tables that don't exist yet, it never ALTERs an existing one. Run this once
instead, after platform_settings.py has been updated with the new columns.

Safe to run more than once: each ALTER is wrapped so an already-applied
column is skipped rather than erroring out.
"""

from sqlalchemy import text

from wsgi import app
from app.extensions import db

NEW_COLUMNS = [
    ("payment_gateway_enabled", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("payment_gateway_provider", "VARCHAR(20) NULL"),
    ("payment_gateway_key_id", "VARCHAR(255) NULL"),
    ("payment_gateway_key_secret", "VARCHAR(500) NULL"),
    ("payment_gateway_webhook_secret", "VARCHAR(500) NULL"),
]

with app.app_context():
    existing_columns = {
        row[0]
        for row in db.session.execute(text("SHOW COLUMNS FROM platform_settings")).fetchall()
    }

    for column_name, ddl_type in NEW_COLUMNS:
        if column_name in existing_columns:
            print(f"Skipping {column_name} - already exists.")
            continue
        db.session.execute(text(f"ALTER TABLE platform_settings ADD COLUMN {column_name} {ddl_type}"))
        print(f"Added column {column_name}.")

    db.session.commit()
    print("Done.")