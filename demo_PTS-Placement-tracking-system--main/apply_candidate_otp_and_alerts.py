"""
apply_candidate_otp_and_alerts.py

Run this from the project root (same folder as wsgi.py), with the venv active:

    python apply_candidate_otp_and_alerts.py

What it does:
  1. Adds OTP verification to candidate login:
       - After password check passes, a 6-digit OTP is emailed to the
         candidate (reuses the existing PasswordResetOTP table and
         _generate_otp() already used for staff forgot-password).
       - New route: /candidate/verify-login-otp (GET/POST), rate-limited.
       - Session ("candidate" dict) is only set after OTP is verified.
       - If a candidate has no email on file, OTP is skipped and they log
         in directly as before (so nobody gets locked out).
  2. Adds a security-alert email on the candidate dashboard's "Update
     Contact & Bank Details" form: if mobile, email, bank name, account
     number, or IFSC change, an email is sent to the OLD email address
     (not the new one) listing what changed, so the real candidate finds
     out even if an attacker changed the email itself.
  3. Creates app/templates/candidate/verify_otp.html, styled to match the
     existing candidate/login.html.

Nothing else about the login or dashboard flow is touched.

Safe to re-run: every step checks whether it was already applied and
skips if so.
"""

import os
import sys

FRONTEND_PY = os.path.join("app", "routes", "frontend.py")
VERIFY_OTP_TEMPLATE = os.path.join("app", "templates", "candidate", "verify_otp.html")


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
# Step 1: candidate login -> OTP
# ---------------------------------------------------------------------------

def patch_login_otp():
    print("Step 1: patching candidate login for OTP verification...")
    content = read_file(FRONTEND_PY)

    if "candidate_verify_login_otp" in content:
        print("  already patched, skipping\n")
        return

    login_anchor = (
        '@frontend_bp.route("/candidate/login", methods=["GET", "POST"])\n'
        'def candidate_login():\n'
        '    error = None\n'
        '    if request.method == "POST":\n'
        '        reg_no = request.form.get("registration_number", "").strip()\n'
        '        password = request.form.get("password", "")\n'
        '\n'
        '        candidate = Candidate.query.filter_by(registration_number=reg_no, is_deleted=False).first()\n'
        '\n'
        '        if not candidate or not candidate.password_hash or not check_password_hash(candidate.password_hash, password):\n'
        '            error = "Invalid registration number or password"\n'
        '        elif candidate.account_status == "blocked":\n'
        '            error = "Your account has been blocked. Please contact your training center."\n'
        '        else:\n'
        '            from datetime import datetime\n'
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
        '\n'
        '    return render_template("candidate/login.html", error=error)\n'
    )
    if login_anchor not in content:
        fail("Could not find the candidate_login() function in frontend.py - it may have changed since this script was written.")

    login_replacement = (
        '@frontend_bp.route("/candidate/login", methods=["GET", "POST"])\n'
        'def candidate_login():\n'
        '    error = None\n'
        '    if request.method == "POST":\n'
        '        reg_no = request.form.get("registration_number", "").strip()\n'
        '        password = request.form.get("password", "")\n'
        '\n'
        '        candidate = Candidate.query.filter_by(registration_number=reg_no, is_deleted=False).first()\n'
        '\n'
        '        if not candidate or not candidate.password_hash or not check_password_hash(candidate.password_hash, password):\n'
        '            error = "Invalid registration number or password"\n'
        '        elif candidate.account_status == "blocked":\n'
        '            error = "Your account has been blocked. Please contact your training center."\n'
        '        elif not candidate.email:\n'
        '            # No email on file - can\'t send an OTP, so fall back to the\n'
        '            # old direct-login behaviour instead of locking the candidate out.\n'
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
        '        else:\n'
        '            from app.utils.email import send_otp_email\n'
        '\n'
        '            otp_code = _generate_otp()\n'
        '            otp_entry = PasswordResetOTP(\n'
        '                email=candidate.email,\n'
        '                otp_code=otp_code,\n'
        '                expires_at=datetime.utcnow() + timedelta(minutes=10),\n'
        '            )\n'
        '            db.session.add(otp_entry)\n'
        '            db.session.commit()\n'
        '\n'
        '            try:\n'
        '                send_otp_email(candidate.email, otp_code)\n'
        '            except Exception:\n'
        '                error = "Could not send OTP email. Please try again later."\n'
        '                return render_template("candidate/login.html", error=error)\n'
        '\n'
        '            session["candidate_otp_pending_id"] = candidate.id\n'
        '            session["candidate_otp_email"] = candidate.email\n'
        '            flash("An OTP has been sent to your registered email address", "success")\n'
        '            return redirect(url_for("frontend.candidate_verify_login_otp"))\n'
        '\n'
        '    return render_template("candidate/login.html", error=error)\n'
        '\n'
        '\n'
        '@frontend_bp.route("/candidate/verify-login-otp", methods=["GET", "POST"])\n'
        '@rate_limit("candidate_verify_login_otp", max_attempts=5, window_seconds=600)\n'
        'def candidate_verify_login_otp():\n'
        '    error = None\n'
        '    candidate_id = session.get("candidate_otp_pending_id")\n'
        '    email = session.get("candidate_otp_email")\n'
        '\n'
        '    if not candidate_id or not email:\n'
        '        flash("Please log in again", "error")\n'
        '        return redirect(url_for("frontend.candidate_login"))\n'
        '\n'
        '    if request.method == "POST":\n'
        '        entered_otp = request.form.get("otp", "").strip()\n'
        '\n'
        '        otp_entry = (\n'
        '            PasswordResetOTP.query.filter_by(email=email, otp_code=entered_otp, is_used=False)\n'
        '            .order_by(PasswordResetOTP.created_at.desc())\n'
        '            .first()\n'
        '        )\n'
        '\n'
        '        if not otp_entry or not otp_entry.is_valid():\n'
        '            error = "Invalid or expired OTP. Please try again."\n'
        '        else:\n'
        '            otp_entry.is_used = True\n'
        '\n'
        '            candidate = Candidate.query.get(candidate_id)\n'
        '            candidate.last_login_at = datetime.utcnow()\n'
        '            db.session.commit()\n'
        '\n'
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
        '\n'
        '    return render_template("candidate/verify_otp.html", error=error, email=email)\n'
    )

    content = content.replace(login_anchor, login_replacement, 1)
    write_file(FRONTEND_PY, content)
    print("  added OTP step to candidate login + /candidate/verify-login-otp route\n")


# ---------------------------------------------------------------------------
# Step 2: update-confirmation security email
# ---------------------------------------------------------------------------

def patch_update_alert():
    print("Step 2: patching candidate_dashboard() for update-confirmation email...")
    content = read_file(FRONTEND_PY)

    if "sensitive_changed" in content:
        print("  already patched, skipping\n")
        return

    update_anchor = (
        '    if request.method == "POST":\n'
        '        candidate.mobile = request.form.get("mobile")\n'
        '        candidate.alternative_mobile = request.form.get("alternative_mobile")\n'
        '        candidate.email = request.form.get("email")\n'
        '        candidate.current_address = request.form.get("current_address")\n'
        '        candidate.permanent_address = request.form.get("permanent_address")\n'
        '        candidate.bank_name = request.form.get("bank_name")\n'
        '        candidate.account_number = request.form.get("account_number")\n'
        '        candidate.ifsc = request.form.get("ifsc")\n'
        '        db.session.commit()\n'
        '        flash("Your details have been updated successfully", "success")\n'
        '        return redirect(url_for("frontend.candidate_dashboard"))\n'
    )
    if update_anchor not in content:
        fail("Could not find the candidate_dashboard() update block in frontend.py - it may have changed since this script was written.")

    update_replacement = (
        '    if request.method == "POST":\n'
        '        old_email = candidate.email\n'
        '        old_mobile = candidate.mobile\n'
        '        old_bank_name = candidate.bank_name\n'
        '        old_account_number = candidate.account_number\n'
        '        old_ifsc = candidate.ifsc\n'
        '\n'
        '        new_mobile = request.form.get("mobile")\n'
        '        new_alternative_mobile = request.form.get("alternative_mobile")\n'
        '        new_email = request.form.get("email")\n'
        '        new_current_address = request.form.get("current_address")\n'
        '        new_permanent_address = request.form.get("permanent_address")\n'
        '        new_bank_name = request.form.get("bank_name")\n'
        '        new_account_number = request.form.get("account_number")\n'
        '        new_ifsc = request.form.get("ifsc")\n'
        '\n'
        '        sensitive_changed = (\n'
        '            old_mobile != new_mobile\n'
        '            or old_email != new_email\n'
        '            or old_bank_name != new_bank_name\n'
        '            or old_account_number != new_account_number\n'
        '            or old_ifsc != new_ifsc\n'
        '        )\n'
        '\n'
        '        candidate.mobile = new_mobile\n'
        '        candidate.alternative_mobile = new_alternative_mobile\n'
        '        candidate.email = new_email\n'
        '        candidate.current_address = new_current_address\n'
        '        candidate.permanent_address = new_permanent_address\n'
        '        candidate.bank_name = new_bank_name\n'
        '        candidate.account_number = new_account_number\n'
        '        candidate.ifsc = new_ifsc\n'
        '        db.session.commit()\n'
        '\n'
        '        # Security alert - sent to the OLD email address (before this\n'
        '        # update), not the new one, so that if an attacker changed the\n'
        '        # email itself the real candidate still finds out. Never blocks\n'
        '        # the save, matching the welcome-email pattern used on creation.\n'
        '        if sensitive_changed and old_email:\n'
        '            from app.services.messaging_service import send_email\n'
        '\n'
        '            changed_fields = []\n'
        '            if old_mobile != new_mobile:\n'
        '                changed_fields.append("Mobile Number")\n'
        '            if old_email != new_email:\n'
        '                changed_fields.append("Email Address")\n'
        '            if old_bank_name != new_bank_name:\n'
        '                changed_fields.append("Bank Name")\n'
        '            if old_account_number != new_account_number:\n'
        '                changed_fields.append("Account Number")\n'
        '            if old_ifsc != new_ifsc:\n'
        '                changed_fields.append("IFSC Code")\n'
        '\n'
        '            alert_subject = "Your Account Details Were Updated"\n'
        '            alert_body = (\n'
        '                f"Dear {candidate.full_name},\\n\\n"\n'
        '                f"The following details on your candidate account were just updated:\\n"\n'
        '                f"{\', \'.join(changed_fields)}\\n\\n"\n'
        '                f"If you made this change, you can ignore this email.\\n"\n'
        '                f"If you did NOT make this change, please contact your training "\n'
        '                f"center immediately to secure your account.\\n\\n"\n'
        '                f"Regards,\\nPlacement Tracking Team"\n'
        '            )\n'
        '            send_email(\n'
        '                old_email,\n'
        '                alert_subject,\n'
        '                alert_body,\n'
        '                organization_id=candidate.organization_id,\n'
        '                candidate_id=candidate.id,\n'
        '            )\n'
        '\n'
        '        flash("Your details have been updated successfully", "success")\n'
        '        return redirect(url_for("frontend.candidate_dashboard"))\n'
    )

    content = content.replace(update_anchor, update_replacement, 1)
    write_file(FRONTEND_PY, content)
    print("  added update-confirmation security email\n")


# ---------------------------------------------------------------------------
# Step 3: template
# ---------------------------------------------------------------------------

def create_template():
    print("Step 3: creating app/templates/candidate/verify_otp.html...")
    if os.path.exists(VERIFY_OTP_TEMPLATE):
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
          <h2 style="margin:0;">Verify OTP</h2>
          <p style="margin:0; color:var(--muted);">Enter the OTP sent to {{ email }}</p>
        </div>
      </div>

      {% if error %}
      <p class="form-error">{{ error }}</p>
      {% endif %}

      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}

      <form method="post" class="auth-form">
        <input type="text" name="otp" placeholder="6-digit OTP" maxlength="6" pattern="[0-9]{6}" required autocomplete="one-time-code">
        <button type="submit" class="primary-btn">Verify OTP</button>
      </form>

      <p style="margin-top:16px; font-size:0.85rem; color:var(--muted);">
        <a href="{{ url_for('frontend.candidate_login') }}">Back to login</a>
      </p>
    </div>
  </div>
</body>
</html>
"""
    write_file(VERIFY_OTP_TEMPLATE, template)
    print("  created verify_otp.html\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Applying candidate login OTP + update-confirmation security email")
    print("=" * 70 + "\n")

    patch_login_otp()
    patch_update_alert()
    create_template()

    print("=" * 70)
    print("All done!")
    print("Restart the Flask server (flask run) to pick up the changes.")
    print("Test flow 1 (login OTP): log in as a candidate with a real email")
    print("  -> should redirect to OTP page -> check inbox -> enter OTP ->")
    print("  dashboard should load.")
    print("Test flow 2 (update alert): from the dashboard, change the mobile")
    print("  number or email -> save -> check the OLD email inbox for the")
    print("  'Your Account Details Were Updated' alert.")
    print("=" * 70)