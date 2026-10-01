"""
Adds separate key columns for each payment provider (Stripe / Razorpay /
Cashfree) to platform_settings, so switching provider in the dropdown never
overwrites another provider's saved keys.

Also copies the OLD single set of keys (payment_gateway_key_id / key_secret /
webhook_secret) into the columns of whichever provider is currently selected,
so nothing already saved is lost.

Safe to run more than once.
Run from project root:  python add_payment_gateway_provider_columns.py
"""

from sqlalchemy import text

from wsgi import app
from app.extensions import db

PROVIDERS = ("stripe", "razorpay", "cashfree")
FIELDS = (
    ("key_id", "VARCHAR(255) NULL"),
    ("key_secret", "VARCHAR(500) NULL"),
    ("webhook_secret", "VARCHAR(500) NULL"),
)

with app.app_context():
    existing_columns = {
        row[0]
        for row in db.session.execute(text("SHOW COLUMNS FROM platform_settings")).fetchall()
    }

    # 1. Add the 9 new columns
    for provider in PROVIDERS:
        for field, ddl_type in FIELDS:
            column_name = f"payment_gateway_{provider}_{field}"
            if column_name in existing_columns:
                print(f"Skipping {column_name} - already exists.")
                continue
            db.session.execute(text(f"ALTER TABLE platform_settings ADD COLUMN {column_name} {ddl_type}"))
            print(f"Added column {column_name}.")
    db.session.commit()

    # 2. Backfill from the old single set of columns
    legacy = db.session.execute(text(
        "SELECT payment_gateway_provider, payment_gateway_key_id, "
        "payment_gateway_key_secret, payment_gateway_webhook_secret "
        "FROM platform_settings WHERE id = 'platform'"
    )).fetchone()

    if legacy and legacy[0] in PROVIDERS:
        provider = legacy[0]
        for field, old_value in zip(("key_id", "key_secret", "webhook_secret"), legacy[1:]):
            if not old_value:
                continue
            column_name = f"payment_gateway_{provider}_{field}"
            db.session.execute(
                text(
                    f"UPDATE platform_settings SET {column_name} = :val "
                    f"WHERE id = 'platform' AND {column_name} IS NULL"
                ),
                {"val": old_value},
            )
            print(f"Copied old {field} into {column_name}.")
        db.session.commit()
    else:
        print("No legacy provider selected - nothing to copy.")

    print("Done.")
