"""
One-time migration: adds a 'batch.view_all' row to the 'permissions' table.

The batches route (organization_batches) already checks for this permission
code via has_permission(user, "batch.view_all") to decide whether a user
sees every batch in their organization (vs only the ones they created) and
whether the "Created By" column is shown. The permission code just didn't
exist as a row yet, so it couldn't be assigned to any role from the
Super Admin > Roles & Permissions screen.

Safe to re-run: skips if the row already exists.
"""

import uuid
from datetime import datetime

from sqlalchemy import text

from wsgi import app
from app.extensions import db


def run():
    with db.engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM permissions WHERE code = 'batch.view_all'
        """))
        exists = result.scalar() > 0

        if exists:
            print("Permission 'batch.view_all' already exists. Nothing to do.")
            return

        new_id = uuid.uuid4().hex
        new_public_id = str(uuid.uuid4())
        now = datetime.utcnow()

        conn.execute(
            text("""
                INSERT INTO permissions (id, public_id, code, description, is_deleted, created_at, updated_at)
                VALUES (:id, :public_id, :code, :description, 0, :created_at, :updated_at)
            """),
            {
                "id": new_id,
                "public_id": new_public_id,
                "code": "batch.view_all",
                "description": "View all batches in the organization, not just ones you created",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
        print("Added 'batch.view_all' permission.")


if __name__ == "__main__":
    with app.app_context():
        run()
