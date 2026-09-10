"""
One-time migration: adds the 'candidate_id' column to the existing
'notifications' table. db.create_all() only creates tables that don't
exist yet - it never alters an existing table's schema, which is why
this needs a manual ALTER.

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
              AND table_name = 'notifications'
              AND column_name = 'candidate_id'
        """))
        exists = result.scalar() > 0

        if exists:
            print("Column 'candidate_id' already exists on 'notifications'. Nothing to do.")
            return

        conn.execute(text("""
            ALTER TABLE notifications
            ADD COLUMN candidate_id CHAR(32) NULL AFTER user_id,
            ADD INDEX idx_notifications_candidate_id (candidate_id),
            ADD CONSTRAINT fk_notifications_candidate_id
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
        """))
        conn.commit()
        print("Added 'candidate_id' column to 'notifications'.")


if __name__ == "__main__":
    with app.app_context():
        run()