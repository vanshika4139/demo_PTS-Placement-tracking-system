"""
Adds created_by / modified_by audit columns to the RBAC tables that were
created before this pattern was established: roles, permissions,
role_permissions, user_permission_overrides.

SAFE BY DESIGN:
- Only ADD COLUMN, never DROP or MODIFY existing columns.
- All new columns are nullable, so existing rows are unaffected.
- Idempotent: checks if a column already exists before adding it.
"""

from sqlalchemy import text

from wsgi import app
from app.extensions import db

TABLES_TO_UPDATE = ["roles", "permissions", "role_permissions", "user_permission_overrides"]


def column_exists(connection, table_name, column_name):
    result = connection.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :table_name AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar() > 0


with app.app_context():
    with db.engine.begin() as connection:
        for table_name in TABLES_TO_UPDATE:
            for column_name in ["created_by", "modified_by"]:
                if column_exists(connection, table_name, column_name):
                    print(f"SKIP: {table_name}.{column_name} already exists.")
                    continue
                connection.execute(
                    text(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` CHAR(32) NULL")
                )
                print(f"ADDED: {table_name}.{column_name}")

    print("\nMigration complete. No existing data was modified or deleted.")