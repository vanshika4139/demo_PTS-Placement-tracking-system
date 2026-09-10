"""
One-time migration: adds the 'is_deleted' column to the existing
'organizations' table, to support soft-delete separately from the
existing 'status' column (which is used for suspend/activate).

status=1/0      -> Active / Suspended (temporary, reversible)
is_deleted=True -> Soft-deleted (permanent-intent, hidden from lists)

Safe to re-run: skips if the column already exists.
"""

from sqlalchemy import text

from wsgi import app
from app.extensions import db


def run():
    with db.engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'organizations'
              AND column_name = 'is_deleted'
        """))
        exists = result.scalar() > 0

        if exists:
            print("Column 'is_deleted' already exists on 'organizations'. Nothing to do.")
            return

        conn.execute(text("""
            ALTER TABLE organizations
            ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0 AFTER status
        """))
        conn.commit()
        print("Added 'is_deleted' column to 'organizations'.")


if __name__ == "__main__":
    with app.app_context():
        run()