"""
Applies the "add created_by to schemes" migration using the same DB
credentials already configured in .env (DATABASE_URL) - no need to have
the mysql.exe CLI on your PATH.

Run from your project root (venv active):
    python run_scheme_migration.py
"""
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not found in .env - aborting.")
    sys.exit(1)

engine = create_engine(db_url)

statements = [
    "ALTER TABLE schemes ADD COLUMN created_by CHAR(32) NULL AFTER description",
    "ALTER TABLE schemes ADD INDEX idx_schemes_created_by (created_by)",
    "ALTER TABLE schemes ADD CONSTRAINT fk_schemes_created_by "
    "FOREIGN KEY (created_by) REFERENCES users(id)",
]

with engine.connect() as conn:
    for stmt in statements:
        print(f"Running: {stmt}")
        conn.execute(text(stmt))
        conn.commit()

print("Done. schemes.created_by column added successfully.")