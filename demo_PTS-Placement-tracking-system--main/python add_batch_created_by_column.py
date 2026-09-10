"""
One-time migration: adds the 'created_by' column to the existing 'batches'
table. db.create_all() only creates tables that don't exist yet - it never
alters an existing table's schema, which is why this needs a manual ALTER.

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
              AND table_name = 'batches'
              AND column_name = 'created_by'
        """))
        exists = result.scalar() > 0

        if exists:
            print("Column 'created_by' already exists on 'batches'. Nothing to do.")
            return

        conn.execute(text("""
            ALTER TABLE batches
            ADD COLUMN created_by CHAR(32) NULL,
            ADD INDEX idx_batches_created_by (created_by),
            ADD CONSTRAINT fk_batches_created_by
                FOREIGN KEY (created_by) REFERENCES users(id)
        """))
        conn.commit()
        print("Added 'created_by' column to 'batches'.")


if __name__ == "__main__":
    with app.app_context():
        run()