"""
apply_candidate_password_setup.py

Run this from the project root (same folder as wsgi.py), with the venv active:

    python apply_candidate_password_setup.py

What it does:
  1. Adds two columns to the `candidates` table (MySQL):
       password_reset_token   VARCHAR(255) NULL
       password_reset_expiry  DATETIME NULL
     (skipped automatically if they already exist - safe to re-run)
  2. Adds the matching fields to app/models/candidate.py
  3. Updates the candidate-creation route (organization_candidate_create) to
     generate a token and include a "Set Your Password" link in the welcome
     email, alongside the existing welcome text.
  4. Adds a new route: GET/POST /candidate/set-password/<token>
  5. Creates app/templates/candidate/set_password.html, styled to match
     the existing candidate/login.html (login-shell / login-card / auth-form).

Nothing about the existing "mobile number = default password" fallback is
touched - this only adds an additional, opt-in way for new candidates to
set their own password via the emailed link.

Safe to re-run: every step checks whether it was already applied and skips
if so, so running this twice won't double-patch anything.
"""

import os
import re
import sys
from urllib.parse import unquote, urlparse

FRONTEND_PY = os.path.join("app", "routes", "frontend.py")
CANDIDATE_MODEL_PY = os.path.join("app", "models", "candidate.py")
SET_PASSWORD_TEMPLATE = os.path.join("app", "templates", "candidate", "set_password.html")
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
# Step 1: DB columns
# ---------------------------------------------------------------------------

def run_db_migration():
    print("Step 1: checking/adding database columns...")
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
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'candidates'
                  AND COLUMN_NAME IN ('password_reset_token', 'password_reset_expiry')
                """,
                (parsed.path.lstrip("/"),),
            )
            existing = {row[0] for row in cur.fetchall()}

            if "password_reset_token" not in existing:
                cur.execute("ALTER TABLE candidates ADD COLUMN password_reset_token VARCHAR(255) NULL")
                print("  added column: password_reset_token")
            else:
                print("  password_reset_token already exists, skipping")

            if "password_reset_expiry" not in existing:
                cur.execute("ALTER TABLE candidates ADD COLUMN password_reset_expiry DATETIME NULL")
                print("  added column: password_reset_expiry")
            else:
                print("  password_reset_expiry already exists, skipping")

        conn.commit()
    finally:
        conn.close()
    print("Step 1 done.\n")


# ---------------------------------------------------------------------------
# Step 2: Candidate model
# ---------------------------------------------------------------------------

def patch_candidate_model():
    print("Step 2: patching app/models/candidate.py...")
    content = read_file(CANDIDATE_MODEL_PY)

    if "password_reset_token" in content:
        print("  already patched, skipping\n")
        return

    anchor = '    password_hash = Column(String(255), nullable=True)\n'
    if anchor not in content:
        fail("Could not find password_hash column line in candidate.py - model may have changed.")

    replacement = (
        anchor
        + '    password_reset_token = Column(String(255), nullable=True)\n'
        + '    password_reset_expiry = Column(DateTime, nullable=True)\n'
    )
    content = content.replace(anchor, replacement, 1)
    write_file(CANDIDATE_MODEL_PY, content)
    print("  added password_reset_token / password_reset_expiry fields\n")


# ---------------------------------------------------------------------------
# Step 3 + 4: frontend.py - import, creation route, new route
# ---------------------------------------------------------------------------

def patch_frontend_py():
    print("Step 3: patching app/routes/frontend.py...")
    content = read_file(FRONTEND_PY)

    if "candidate_set_password" in content:
        print("  already patched, skipping\n")
        return

    # --- 3a. import secrets ---
    import_anchor = "import random\nimport string\n"
    if import_anchor not in content:
        fail("Could not find 'import random / import string' block at top of frontend.py.")
    content = content.replace(
        import_anchor,
        "import random\nimport secrets\nimport string\n",
        1,
    )
    print("  added `import secrets`")

    # --- 3b. creation route: generate token + add link to welcome email ---
    creation_anchor = (
        '        db.session.add(candidate)\n'
        '        db.session.commit()\n'
        '\n'
        '        # Welcome email - sent immediately on candidate creation, not via\n'
        '        # the scheduled NotificationSchedule system (that\'s for recurring\n'
        '        # reminders). Failure here should never break candidate creation,\n'
        '        # so it\'s wrapped and only logged, matching the pattern used\n'
        '        # elsewhere in this app (see messaging_service.send_email itself,\n'
        '        # which also never raises).\n'
        '        if candidate.email:\n'
        '            from app.services.messaging_service import send_email\n'
        '            welcome_subject = "Welcome to the Placement Program"\n'
        '            welcome_body = (\n'
        '                f"Dear {candidate.full_name},\\n\\n"\n'
        '                f"Welcome to the Placement Tracking System! Your registration "\n'
        '                f"has been completed successfully.\\n\\n"\n'
        '                f"Registration Number: {candidate.registration_number or \'Not assigned yet\'}\\n"\n'
        '                f"Training Center: {candidate.training_center or \'Not assigned yet\'}\\n\\n"\n'
        '                f"We wish you the best for your training and placement journey.\\n\\n"\n'
        '                f"Regards,\\nPlacement Tracking Team"\n'
        '            )\n'
        '            send_email(\n'
        '                candidate.email,\n'
        '                welcome_subject,\n'
        '                welcome_body,\n'
        '                organization_id=candidate.organization_id,\n'
        '                candidate_id=candidate.id,\n'
        '            )\n'
    )
    if creation_anchor not in content:
        fail("Could not find the candidate-creation / welcome-email block in frontend.py - it may have changed since this script was written.")

    creation_replacement = (
        '        db.session.add(candidate)\n'
        '        db.session.commit()\n'
        '\n'
        '        # Password-setup token - generated right after creation so new\n'
        '        # candidates get a "Set Your Password" link in their welcome email\n'
        '        # instead of only the mobile-number-as-password fallback. The\n'
        '        # existing mobile-number default password is untouched (still used\n'
        '        # elsewhere, e.g. org-admin Reset Password).\n'
        '        reset_token = secrets.token_urlsafe(32)\n'
        '        candidate.password_reset_token = reset_token\n'
        '        candidate.password_reset_expiry = datetime.utcnow() + timedelta(hours=24)\n'
        '        db.session.commit()\n'
        '\n'
        '        # Welcome email - sent immediately on candidate creation, not via\n'
        '        # the scheduled NotificationSchedule system (that\'s for recurring\n'
        '        # reminders). Failure here should never break candidate creation,\n'
        '        # so it\'s wrapped and only logged, matching the pattern used\n'
        '        # elsewhere in this app (see messaging_service.send_email itself,\n'
        '        # which also never raises).\n'
        '        if candidate.email:\n'
        '            from app.services.messaging_service import send_email\n'
        '            set_password_url = url_for("frontend.candidate_set_password", token=reset_token, _external=True)\n'
        '            welcome_subject = "Welcome to the Placement Program"\n'
        '            welcome_body = (\n'
        '                f"Dear {candidate.full_name},\\n\\n"\n'
        '                f"Welcome to the Placement Tracking System! Your registration "\n'
        '                f"has been completed successfully.\\n\\n"\n'
        '                f"Registration Number: {candidate.registration_number or \'Not assigned yet\'}\\n"\n'
        '                f"Training Center: {candidate.training_center or \'Not assigned yet\'}\\n\\n"\n'
        '                f"Please set your password using the link below (valid for 24 hours):\\n"\n'
        '                f"{set_password_url}\\n\\n"\n'
        '                f"We wish you the best for your training and placement journey.\\n\\n"\n'
        '                f"Regards,\\nPlacement Tracking Team"\n'
        '            )\n'
        '            send_email(\n'
        '                candidate.email,\n'
        '                welcome_subject,\n'
        '                welcome_body,\n'
        '                organization_id=candidate.organization_id,\n'
        '                candidate_id=candidate.id,\n'
        '            )\n'
    )
    content = content.replace(creation_anchor, creation_replacement, 1)
    print("  updated candidate-creation route (token + email link)")

    # --- 3c. new route, inserted right before /candidate/logout ---
    route_anchor = (
        '    return render_template("candidate/login.html", error=error)\n'
        '\n'
        '\n'
        '@frontend_bp.route("/candidate/logout")\n'
    )
    if route_anchor not in content:
        fail("Could not find the end of candidate_login() / start of /candidate/logout in frontend.py.")

    new_route = (
        '    return render_template("candidate/login.html", error=error)\n'
        '\n'
        '\n'
        '@frontend_bp.route("/candidate/set-password/<token>", methods=["GET", "POST"])\n'
        'def candidate_set_password(token):\n'
        '    """Lets a newly-created candidate set their own password via the\n'
        '    link emailed to them on creation. Token is single-use (cleared on\n'
        '    success) and expires 24 hours after the candidate was created."""\n'
        '    candidate = Candidate.query.filter_by(password_reset_token=token, is_deleted=False).first()\n'
        '\n'
        '    if not candidate or not candidate.password_reset_expiry or candidate.password_reset_expiry < datetime.utcnow():\n'
        '        return render_template(\n'
        '            "candidate/set_password.html",\n'
        '            error="This link is invalid or has expired. Please contact your training center for a new one.",\n'
        '            invalid=True,\n'
        '        )\n'
        '\n'
        '    error = None\n'
        '    if request.method == "POST":\n'
        '        password = request.form.get("password") or ""\n'
        '        confirm_password = request.form.get("confirm_password") or ""\n'
        '\n'
        '        if len(password) < 6:\n'
        '            error = "Password must be at least 6 characters long."\n'
        '        elif password != confirm_password:\n'
        '            error = "Passwords do not match."\n'
        '        else:\n'
        '            candidate.password_hash = generate_password_hash(password)\n'
        '            candidate.password_reset_token = None\n'
        '            candidate.password_reset_expiry = None\n'
        '            db.session.commit()\n'
        '            flash("Password set successfully. Please log in.", "success")\n'
        '            return redirect(url_for("frontend.candidate_login"))\n'
        '\n'
        '    return render_template("candidate/set_password.html", error=error, invalid=False)\n'
        '\n'
        '\n'
        '@frontend_bp.route("/candidate/logout")\n'
    )
    content = content.replace(route_anchor, new_route, 1)
    print("  added /candidate/set-password/<token> route")

    write_file(FRONTEND_PY, content)
    print("Step 3 done.\n")


# ---------------------------------------------------------------------------
# Step 5: template
# ---------------------------------------------------------------------------

def create_template():
    print("Step 5: creating app/templates/candidate/set_password.html...")
    if os.path.exists(SET_PASSWORD_TEMPLATE):
        print("  already exists, skipping\n")
        return

    template = """<!doctype html>
<html lang="{{ current_language() }}">
<head>
  <meta charset="utf-8">
  <title>{{ _('candidate_portal') }}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
</head>
<body>
  <div class="login-shell">
    <div class="login-card">
      <div class="brand-block" style="margin-bottom:16px;">
        <div class="brand-mark large">C</div>
        <div>
          <h2 style="margin:0;">Set Your Password</h2>
          <p style="margin:0; color:var(--muted);">Choose a password for your candidate account</p>
        </div>
      </div>

      {% if error %}
      <p class="form-error">{{ error }}</p>
      {% endif %}

      {% if not invalid %}
      <form method="post" class="auth-form">
        <input type="password" name="password" placeholder="New Password" required minlength="6">
        <input type="password" name="confirm_password" placeholder="Confirm Password" required minlength="6">
        <button type="submit" class="primary-btn">Set Password</button>
      </form>
      {% endif %}

      <p style="margin-top:16px; font-size:0.85rem; color:var(--muted);">
        <a href="{{ url_for('frontend.candidate_login') }}">Back to login</a>
      </p>
    </div>
  </div>
</body>
</html>
"""
    write_file(SET_PASSWORD_TEMPLATE, template)
    print("  created set_password.html\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Applying candidate password-setup feature")
    print("=" * 70 + "\n")

    run_db_migration()
    patch_candidate_model()
    patch_frontend_py()
    create_template()

    print("=" * 70)
    print("All done!")
    print("Restart the Flask server (flask run) to pick up the changes.")
    print("Test flow: create a new candidate with a real email -> check the")
    print("welcome email for the 'Set Your Password' link -> open it ->")
    print("set a password -> log in at /candidate/login with it.")
    print("=" * 70)