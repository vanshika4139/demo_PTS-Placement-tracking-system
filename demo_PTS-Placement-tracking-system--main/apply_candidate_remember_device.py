"""
apply_candidate_remember_device.py

Run this from the project root (same folder as wsgi.py), with the venv active:

    python apply_candidate_remember_device.py

What it does:
  1. Creates a new table `candidate_trusted_devices` (MySQL) - stores a
     hashed token per "remembered" device, never the raw token.
  2. Creates app/models/candidate_trusted_device.py and registers it in
     app/models/__init__.py
  3. Adds a "Remember this device for 30 days" checkbox to the OTP
     verification page. If checked, a signed cookie is set on success.
  4. On the next candidate login, if a valid trusted-device cookie is
     found (and it actually belongs to that candidate, checked against
     the hashed token in the DB), the OTP step is skipped entirely.

Security notes:
  - Only a random token is stored in the cookie; the DB only ever stores
    its SHA-256 hash (same idea as a password hash), so a DB leak alone
    can't be used to forge a trusted-device cookie.
  - The cookie is httponly (not readable by JS) and scoped to this app.
  - Nothing changes for candidates who don't check the box - they still
    get an OTP every login, exactly as before.

Safe to re-run: every step checks whether it was already applied and
skips if so.
"""

import os
import re
import sys
from urllib.parse import unquote, urlparse

FRONTEND_PY = os.path.join("app", "routes", "frontend.py")
MODELS_INIT_PY = os.path.join("app", "models", "__init__.py")
TRUSTED_DEVICE_MODEL_PY = os.path.join("app", "models", "candidate_trusted_device.py")
VERIFY_OTP_TEMPLATE = os.path.join("app", "templates", "candidate", "verify_otp.html")
ENV_FILE = ".env"


def fail(msg):
    print(f"\n[FAILED] {msg}")
    sys.exit(1)


def read_file(path):
    if not os.path.exists(path):
        fail(f"Could not find {path} - run this script from the project root.")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Step 1: DB table
# ---------------------------------------------------------------------------

def run_db_migration():
    print("Step 1: creating candidate_trusted_devices table...")
    try:
        import pymysql
    except ImportError:
        fail("pymysql is not installed in this venv. Run: pip install pymysql")

    env_text = read_file(ENV_FILE)
    match = re.search(r"^DATABASE_URL=(.+)$", env_text, re.MULTILINE)
    if not match:
        fail("Could not find DATABASE_URL in .env")

    db_url = match.group(1).strip()
    parsed = urlparse(db_url.replace("mysql+pymysql://", "mysql://", 1))

    conn = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_trusted_devices (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    candidate_id CHAR(32) NOT NULL,
                    token_hash VARCHAR(255) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_ctd_candidate_id (candidate_id),
                    INDEX idx_ctd_token_hash (token_hash),
                    CONSTRAINT fk_ctd_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id)
                )
                """
            )
        conn.commit()
    finally:
        conn.close()
    print("  candidate_trusted_devices table ready\n")


# ---------------------------------------------------------------------------
# Step 2: model file + registration
# ---------------------------------------------------------------------------

def create_model():
    print("Step 2: creating app/models/candidate_trusted_device.py...")
    if os.path.exists(TRUSTED_DEVICE_MODEL_PY):
        print("  already exists, skipping\n")
    else:
        model_content = '''import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.mysql import CHAR as MySQLCHAR

from app.extensions import db


class CandidateTrustedDevice(db.Model):
    """A 'remembered' browser for a candidate, so they can skip the login
    OTP for 30 days on that device. Only a hash of the device token is
    stored here - the raw token lives only in the candidate's cookie."""

    __tablename__ = "candidate_trusted_devices"

    id = Column(MySQLCHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()).replace("-", ""))
    candidate_id = Column(MySQLCHAR(32), ForeignKey("candidates.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def is_valid(self):
        return datetime.utcnow() <= self.expires_at
'''
        write_file(TRUSTED_DEVICE_MODEL_PY, model_content)
        print("  created candidate_trusted_device.py")

    print("Step 2b: registering it in app/models/__init__.py...")
    content = read_file(MODELS_INIT_PY)
    if "CandidateTrustedDevice" in content:
        print("  already registered, skipping\n")
        return

    import_anchor = "from app.models.candidate_feedback import CandidateFeedback\n"
    if import_anchor not in content:
        fail("Could not find the candidate_feedback import in app/models/__init__.py.")
    content = content.replace(
        import_anchor,
        import_anchor + "from app.models.candidate_trusted_device import CandidateTrustedDevice\n",
        1,
    )

    all_anchor = '    "CandidateFeedback",\n'
    if all_anchor not in content:
        fail("Could not find CandidateFeedback in __all__ in app/models/__init__.py.")
    content = content.replace(
        all_anchor,
        all_anchor + '    "CandidateTrustedDevice",\n',
        1,
    )

    write_file(MODELS_INIT_PY, content)
    print("  registered CandidateTrustedDevice\n")


# ---------------------------------------------------------------------------
# Step 3: frontend.py
# ---------------------------------------------------------------------------

def patch_frontend_py():
    print("Step 3: patching app/routes/frontend.py...")
    content = read_file(FRONTEND_PY)

    if "_is_trusted_device" in content:
        print("  already patched, skipping\n")
        return

    # --- 3a. import hashlib ---
    import_anchor = "import logging\nimport os\n"
    if import_anchor not in content:
        fail("Could not find the top-of-file imports in frontend.py.")
    content = content.replace(import_anchor, "import hashlib\nimport logging\nimport os\n", 1)
    print("  added `import hashlib`")

    # --- 3b. add CandidateTrustedDevice to the models import block ---
    model_import_anchor = "    Candidate,\n    CandidateFeedback,\n"
    if model_import_anchor not in content:
        fail("Could not find Candidate/CandidateFeedback in the models import block.")
    content = content.replace(
        model_import_anchor,
        "    Candidate,\n    CandidateFeedback,\n    CandidateTrustedDevice,\n",
        1,
    )
    print("  added CandidateTrustedDevice to models import")

    # --- 3c. helper functions, right after _generate_otp ---
    otp_helper_anchor = (
        'def _generate_otp():\n'
        '    return "".join(random.choices(string.digits, k=6))\n'
    )
    if otp_helper_anchor not in content:
        fail("Could not find _generate_otp() in frontend.py.")
    content = content.replace(
        otp_helper_anchor,
        otp_helper_anchor
        + '\n'
        + 'def _hash_device_token(token):\n'
        + '    return hashlib.sha256(token.encode()).hexdigest()\n'
        + '\n'
        + '\n'
        + 'def _is_trusted_device(candidate):\n'
        + '    """True if this browser has a valid \'remember this device\' cookie\n'
        + '    for this candidate - lets them skip the login OTP for 30 days."""\n'
        + '    cookie_value = request.cookies.get("candidate_device")\n'
        + '    if not cookie_value or "." not in cookie_value:\n'
        + '        return False\n'
        + '\n'
        + '    cand_id, token = cookie_value.split(".", 1)\n'
        + '    if cand_id != candidate.id:\n'
        + '        return False\n'
        + '\n'
        + '    device = CandidateTrustedDevice.query.filter_by(\n'
        + '        candidate_id=candidate.id, token_hash=_hash_device_token(token)\n'
        + '    ).first()\n'
        + '    return bool(device and device.is_valid())\n',
        1,
    )
    print("  added _hash_device_token() / _is_trusted_device() helpers")

    # --- 3d. candidate_login: skip OTP if device is trusted ---
    login_anchor = (
        '        elif candidate.account_status == "blocked":\n'
        '            error = "Your account has been blocked. Please contact your training center."\n'
        '        elif not candidate.email:\n'
    )
    if login_anchor not in content:
        fail("Could not find the candidate_login() status checks in frontend.py.")
    login_replacement = (
        '        elif candidate.account_status == "blocked":\n'
        '            error = "Your account has been blocked. Please contact your training center."\n'
        '        elif _is_trusted_device(candidate):\n'
        '            candidate.last_login_at = datetime.utcnow()\n'
        '            db.session.commit()\n'
        '\n'
        '            session["candidate"] = {\n'
        '                "id": candidate.id,\n'
        '                "full_name": candidate.full_name,\n'
        '                "registration_number": candidate.registration_number,\n'
        '            }\n'
        '            session.permanent = True\n'
        '            flash(f"Welcome, {candidate.full_name}", "success")\n'
        '            return redirect(url_for("frontend.candidate_dashboard"))\n'
        '        elif not candidate.email:\n'
    )
    content = content.replace(login_anchor, login_replacement, 1)
    print("  candidate_login now skips OTP for trusted devices")

    # --- 3e. candidate_verify_login_otp: set the cookie on success ---
    otp_success_anchor = (
        '            session.pop("candidate_otp_pending_id", None)\n'
        '            session.pop("candidate_otp_email", None)\n'
        '            session["candidate"] = {\n'
        '                "id": candidate.id,\n'
        '                "full_name": candidate.full_name,\n'
        '                "registration_number": candidate.registration_number,\n'
        '            }\n'
        '            session.permanent = True\n'
        '            flash(f"Welcome, {candidate.full_name}", "success")\n'
        '            return redirect(url_for("frontend.candidate_dashboard"))\n'
    )
    if otp_success_anchor not in content:
        fail("Could not find the candidate_verify_login_otp() success block in frontend.py.")
    otp_success_replacement = (
        '            session.pop("candidate_otp_pending_id", None)\n'
        '            session.pop("candidate_otp_email", None)\n'
        '            session["candidate"] = {\n'
        '                "id": candidate.id,\n'
        '                "full_name": candidate.full_name,\n'
        '                "registration_number": candidate.registration_number,\n'
        '            }\n'
        '            session.permanent = True\n'
        '            flash(f"Welcome, {candidate.full_name}", "success")\n'
        '\n'
        '            response = redirect(url_for("frontend.candidate_dashboard"))\n'
        '            if request.form.get("remember_device") == "on":\n'
        '                device_token = secrets.token_urlsafe(32)\n'
        '                trusted_device = CandidateTrustedDevice(\n'
        '                    candidate_id=candidate.id,\n'
        '                    token_hash=_hash_device_token(device_token),\n'
        '                    expires_at=datetime.utcnow() + timedelta(days=30),\n'
        '                )\n'
        '                db.session.add(trusted_device)\n'
        '                db.session.commit()\n'
        '                response.set_cookie(\n'
        '                    "candidate_device",\n'
        '                    f"{candidate.id}.{device_token}",\n'
        '                    max_age=30 * 24 * 60 * 60,\n'
        '                    httponly=True,\n'
        '                    samesite="Lax",\n'
        '                )\n'
        '            return response\n'
    )
    content = content.replace(otp_success_anchor, otp_success_replacement, 1)
    print("  candidate_verify_login_otp now sets the trusted-device cookie")

    write_file(FRONTEND_PY, content)
    print("Step 3 done.\n")


# ---------------------------------------------------------------------------
# Step 4: template checkbox
# ---------------------------------------------------------------------------

def patch_template():
    print("Step 4: adding checkbox to candidate/verify_otp.html...")
    content = read_file(VERIFY_OTP_TEMPLATE)

    if "remember_device" in content:
        print("  already patched, skipping\n")
        return

    anchor = (
        '      <form method="post" class="auth-form">\n'
        '        <input type="text" name="otp" placeholder="6-digit OTP" maxlength="6" pattern="[0-9]{6}" required autocomplete="one-time-code">\n'
        '        <button type="submit" class="primary-btn">Verify OTP</button>\n'
        '      </form>\n'
    )
    if anchor not in content:
        fail("Could not find the OTP form in candidate/verify_otp.html - it may have changed.")

    replacement = (
        '      <form method="post" class="auth-form">\n'
        '        <input type="text" name="otp" placeholder="6-digit OTP" maxlength="6" pattern="[0-9]{6}" required autocomplete="one-time-code">\n'
        '        <label style="display:flex; align-items:center; gap:8px; font-size:0.85rem; font-weight:normal; margin:4px 0;">\n'
        '          <input type="checkbox" name="remember_device" style="width:auto;">\n'
        '          Remember this device for 30 days\n'
        '        </label>\n'
        '        <button type="submit" class="primary-btn">Verify OTP</button>\n'
        '      </form>\n'
    )
    content = content.replace(anchor, replacement, 1)
    write_file(VERIFY_OTP_TEMPLATE, content)
    print("  added 'Remember this device' checkbox\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Applying candidate 'remember this device' (skip OTP for 30 days)")
    print("=" * 70 + "\n")

    run_db_migration()
    create_model()
    patch_frontend_py()
    patch_template()

    print("=" * 70)
    print("All done!")
    print("Restart the Flask server (flask run) to pick up the changes.")
    print("Test flow: log in as a candidate -> enter OTP -> check 'Remember")
    print("this device for 30 days' -> submit -> log out -> log in again on")
    print("the SAME browser -> should skip straight to the dashboard, no OTP.")
    print("Log in from a different browser (or clear cookies) -> OTP should")
    print("be asked again.")
    print("=" * 70)