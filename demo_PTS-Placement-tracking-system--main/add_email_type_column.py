"""
Migration: adds the 'email_type' column to 'email_logs' and fills it for
existing rows (worked out from each row's subject).

Run AFTER apply_email_types.py. Safe to re-run: skips the column if it
exists, and only fills rows whose email_type is still empty.
Run it on the live server too, once, when you deploy.
"""

from sqlalchemy import text

from wsgi import app
from app.extensions import db

try:
    from app.models.email_log import classify_email_type
except ImportError:
    raise SystemExit("Run apply_email_types.py first (email_log.py has no classify_email_type yet).")


def run():
    with db.engine.connect() as conn:
        exists = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'email_logs'
              AND column_name = 'email_type'
        """)).scalar() > 0

        if exists:
            print("Column 'email_type' already exists on 'email_logs'.")
        else:
            conn.execute(text("""
                ALTER TABLE email_logs
                ADD COLUMN email_type VARCHAR(40) NULL,
                ADD INDEX idx_email_logs_email_type (email_type)
            """))
            conn.commit()
            print("Added 'email_type' column to 'email_logs'.")

        rows = conn.execute(text("SELECT id, subject FROM email_logs WHERE email_type IS NULL")).fetchall()
        if rows:
            conn.execute(
                text("UPDATE email_logs SET email_type = :t WHERE id = :i"),
                [{"t": classify_email_type(subject), "i": log_id} for log_id, subject in rows],
            )
            conn.commit()
        print(f"Filled email_type for {len(rows)} existing row(s).")

        print("\nEmails per type now:")
        for t, c in conn.execute(text(
            "SELECT email_type, COUNT(*) FROM email_logs GROUP BY email_type ORDER BY 2 DESC"
        )):
            print(f"  {c:>4}  {t}")


if __name__ == "__main__":
    with app.app_context():
        run()
