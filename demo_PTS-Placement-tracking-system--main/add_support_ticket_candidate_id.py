"""
One-time migration: adds the 'candidate_id' column to the existing
'support_tickets' table, so a ticket raised from the candidate portal can be
linked back to the candidate (and the candidate can see their own tickets).

Run this BEFORE restarting the app after apply_candidate_help.py.
Safe to re-run: skips if the column already exists.
"""

from sqlalchemy import text

from wsgi import app
from app.extensions import db


def run():
    with db.engine.connect() as conn:
        exists = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'support_tickets'
              AND column_name = 'candidate_id'
        """)).scalar() > 0

        if exists:
            print("Column 'candidate_id' already exists on 'support_tickets'. Nothing to do.")
            return

        conn.execute(text("""
            ALTER TABLE support_tickets
            ADD COLUMN candidate_id VARCHAR(32) NULL,
            ADD INDEX idx_support_tickets_candidate_id (candidate_id)
        """))
        conn.commit()
        print("Added 'candidate_id' column to 'support_tickets'.")


if __name__ == "__main__":
    with app.app_context():
        run()
