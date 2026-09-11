"""
Runs the platform_settings migration directly, using the same DB credentials
your Flask app already uses from .env. Avoids needing mysql.exe on PATH.

Usage (inside your venv, from the project root where .env lives):
    python run_migration.py
"""
import os

import pymysql

# --- Load .env manually (no extra dependency needed) ---
def load_env(path=".env"):
    env = {}
    if not os.path.exists(path):
        print(f"Could not find {path} - run this script from the project "
              f"root (same folder as your .env file), or edit the DB_* "
              f"values below directly.")
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


env = load_env()

DB_HOST = env.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(env.get("MYSQL_PORT", "3306"))
DB_USER = env.get("MYSQL_USER", "root")
DB_PASSWORD = env.get("MYSQL_PASSWORD", "")
DB_NAME = env.get("MYSQL_DATABASE", "placement_tracking")

STATEMENTS = [
    "ALTER TABLE platform_settings ADD COLUMN email_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER id",
    "ALTER TABLE platform_settings ADD COLUMN whatsapp_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER whatsapp_phone_number_id",
    "ALTER TABLE platform_settings ADD COLUMN sms_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER sms_sender_id",
    "ALTER TABLE platform_settings ADD COLUMN voice_call_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER sms_enabled",
    "ALTER TABLE platform_settings ADD COLUMN voice_provider VARCHAR(100) NULL AFTER voice_call_enabled",
    "ALTER TABLE platform_settings ADD COLUMN voice_api_key VARCHAR(500) NULL AFTER voice_provider",
    "ALTER TABLE platform_settings ADD COLUMN voice_caller_id VARCHAR(50) NULL AFTER voice_api_key",
    "ALTER TABLE platform_settings ADD COLUMN push_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER voice_caller_id",
    "ALTER TABLE platform_settings ADD COLUMN push_provider VARCHAR(100) NULL AFTER push_enabled",
    "ALTER TABLE platform_settings ADD COLUMN push_server_key VARCHAR(500) NULL AFTER push_provider",
    "ALTER TABLE platform_settings ADD COLUMN push_sender_id VARCHAR(100) NULL AFTER push_server_key",
]

BACKFILL = """
UPDATE platform_settings
SET email_enabled    = IF(smtp_host IS NOT NULL AND smtp_host != '', 1, email_enabled),
    whatsapp_enabled = IF(whatsapp_api_key IS NOT NULL AND whatsapp_api_key != '', 1, whatsapp_enabled),
    sms_enabled      = IF(sms_api_key IS NOT NULL AND sms_api_key != '', 1, sms_enabled)
WHERE id = 'platform'
"""


def column_exists(cursor, table, column):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (DB_NAME, table, column),
    )
    return cursor.fetchone()[0] > 0


def main():
    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER} ...")
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            for stmt in STATEMENTS:
                # Extract "ADD COLUMN <name>" to skip if it's already there
                # (safe to re-run this script if it fails partway through).
                col_name = stmt.split("ADD COLUMN")[1].strip().split(" ")[0]
                if column_exists(cursor, "platform_settings", col_name):
                    print(f"  skip (already exists): {col_name}")
                    continue
                print(f"  running: {col_name}")
                cursor.execute(stmt)

            print("  running: backfill enabled flags for existing credentials")
            cursor.execute(BACKFILL)

        conn.commit()
        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()