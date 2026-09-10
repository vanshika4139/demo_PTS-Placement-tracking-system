"""
One-time patch: adds Phase 1 of the candidate self-service placement flow.

What this does:
1. Adds a new route `candidate_report_placement` to app/routes/frontend.py,
   right after the existing candidate_upload_proof route. This lets a
   logged-in candidate submit their own employer/job/joining date/salary
   (salary is optional - leaving it blank is how we track "salary pending"
   for Phase 2 later, with no new DB column needed).
2. Overwrites app/templates/candidate/dashboard.html with the same file plus
   a new "Are you currently employed?" section (Yes/No buttons -> reveals a
   placement form on Yes) inserted between the "Update Contact & Bank" card
   and the feedback card.

Safe to re-run:
- frontend.py: skipped if `def candidate_report_placement` already present.
- dashboard.html: skipped if `employment-status-card` already present.

Run this from the project root (same place you ran the other scripts):
    python apply_phase1_candidate_placement.py
"""

import os

FRONTEND_PY_PATH = os.path.join("app", "routes", "frontend.py")
DASHBOARD_HTML_PATH = os.path.join("app", "templates", "candidate", "dashboard.html")

FRONTEND_ANCHOR = '''    flash(translate("proof_upload_success"), "success")
    return redirect(url_for("frontend.candidate_dashboard"))


@frontend_bp.route("/organization/feedback")'''

FRONTEND_NEW_BLOCK = '''    flash(translate("proof_upload_success"), "success")
    return redirect(url_for("frontend.candidate_dashboard"))


@frontend_bp.route("/candidate/report-placement", methods=["POST"])
@candidate_login_required
def candidate_report_placement():
    session_candidate = session.get("candidate")
    candidate = Candidate.query.get_or_404(session_candidate.get("id"))

    if candidate.employer_name:
        flash("Your placement details are already recorded.", "info")
        return redirect(url_for("frontend.candidate_dashboard"))

    employer_name = (request.form.get("employer_name") or "").strip()
    job_role = (request.form.get("job_role") or "").strip()
    joining_date = _parse_date(request.form.get("joining_date"))
    location = (request.form.get("location") or "").strip()
    salary = (request.form.get("salary") or "").strip()

    if not employer_name or not job_role or not joining_date:
        flash("Please fill Employer Name, Job Role, and Joining Date.", "error")
        return redirect(url_for("frontend.candidate_dashboard"))

    candidate.employer_name = employer_name
    candidate.job_role = job_role
    candidate.joining_date = joining_date
    candidate.location = location or None
    candidate.salary = salary or None
    candidate.working_status = "Working"
    db.session.commit()

    _ensure_checkpoints(candidate)

    invalidate_report_cache("reports")
    invalidate_report_cache("dashboard:org")
    invalidate_report_cache("dashboard:super_admin")

    _create_notification(
        title=f"Candidate self-reported placement: {candidate.full_name}",
        message=(
            f"{candidate.full_name} reported they joined {employer_name} as {job_role}."
            + ("" if salary else " Salary was not provided yet.")
        ),
        notif_type="success" if salary else "warning",
        organization_id=candidate.organization_id,
        candidate_id=candidate.id,
    )
    _send_placement_email(candidate)

    flash("Thank you! Your placement details have been saved.", "success")
    return redirect(url_for("frontend.candidate_dashboard"))


@frontend_bp.route("/organization/feedback")'''


DASHBOARD_HTML_FULL = r'''<!doctype html>
<html lang="{{ current_language() }}">
<head>
  <meta charset="utf-8">
  <title>{{ _('my_details_readonly') }}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/forms.css') }}">
</head>
<body>
  <div class="page-content" style="max-width:900px; margin:0 auto;">

    <div style="text-align:right; font-size:0.82rem; margin-bottom:8px;">
      <a href="{{ url_for('frontend.set_language', lang_code='en') }}"
         style="text-decoration:none; {{ 'font-weight:700; color:var(--avocado-dark);' if current_language() == 'en' else 'color:var(--muted);' }}">EN</a>
      &nbsp;|&nbsp;
      <a href="{{ url_for('frontend.set_language', lang_code='hi') }}"
         style="text-decoration:none; {{ 'font-weight:700; color:var(--avocado-dark);' if current_language() == 'hi' else 'color:var(--muted);' }}">हिं</a>
    </div>

    <div class="page-header page-header-inline">
      <div>
        <h2>{{ _('welcome') }} {{ candidate.full_name }}</h2>
        <p>{{ _('registration_no_label') }} {{ candidate.registration_number or '-' }}</p>
      </div>
      <a href="{{ url_for('frontend.candidate_logout') }}" class="ghost-btn">{{ _('logout') }}</a>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div class="panel-card">
      <h3>{{ _('my_details_readonly') }}</h3>
      <div class="form-grid">
        <label>{{ _('fathers_name') }}<input type="text" value="{{ candidate.father_name or '-' }}" disabled></label>
        <label>{{ _('date_of_birth') }}<input type="text" value="{{ candidate.date_of_birth.strftime('%d-%m-%Y') if candidate.date_of_birth else '-' }}" disabled></label>
        <label>{{ _('aadhaar') }}<input type="text" value="{{ candidate.aadhaar or '-' }}" disabled></label>
        <label>{{ _('training_center') }}<input type="text" value="{{ candidate.training_center or '-' }}" disabled></label>
        <label>{{ _('course') }}<input type="text" value="{{ candidate.course or '-' }}" disabled></label>
        <label>{{ _('training_status') }}<input type="text" value="{{ candidate.training_status or '-' }}" disabled></label>
        <label>{{ _('verification_status') }}<input type="text" value="{{ candidate.verification_status or '-' }}" disabled></label>
        <label>{{ _('employer') }}<input type="text" value="{{ candidate.employer_name or '-' }}" disabled></label>
      </div>
      <p style="margin-top:12px; font-size:0.85rem; color:var(--muted);">{{ _('readonly_note') }}</p>
    </div>

    <div class="panel-card">
      <h3>{{ _('update_contact_bank') }}</h3>
      <form method="post" class="full-form">
        <div class="form-grid">
          <label>{{ _('mobile') }}<input type="text" name="mobile" value="{{ candidate.mobile or '' }}"></label>
          <label>{{ _('alternative_mobile') }}<input type="text" name="alternative_mobile" value="{{ candidate.alternative_mobile or '' }}"></label>
          <label>{{ _('email') }}<input type="email" name="email" value="{{ candidate.email or '' }}"></label>
          <label>{{ _('current_address') }}<input type="text" name="current_address" value="{{ candidate.current_address or '' }}"></label>
          <label>{{ _('permanent_address') }}<input type="text" name="permanent_address" value="{{ candidate.permanent_address or '' }}"></label>
          <label>{{ _('bank_name') }}<input type="text" name="bank_name" value="{{ candidate.bank_name or '' }}"></label>
          <label>{{ _('account_number') }}<input type="text" name="account_number" value="{{ candidate.account_number or '' }}"></label>
          <label>{{ _('ifsc') }}<input type="text" name="ifsc" value="{{ candidate.ifsc or '' }}"></label>
        </div>
        <div class="form-actions">
          <button type="submit" class="primary-btn">{{ _('save_changes') }}</button>
        </div>
      </form>
    </div>

    {% if not candidate.employer_name %}
    <div class="panel-card" id="employment-status-card">
      <h3>Are you currently employed?</h3>
      <p style="color:var(--muted); font-size:0.85rem; margin-top:-6px; margin-bottom:14px;">Let us know your job status so we can update your placement record.</p>

      <div class="es-toggle-buttons" id="es-toggle-buttons" style="display:flex; gap:10px; margin-bottom:14px;">
        <button type="button" id="es-yes-btn" class="primary-btn">Yes, I have a job</button>
        <button type="button" id="es-no-btn" class="ghost-btn">Not yet</button>
      </div>

      <p id="es-no-message" style="display:none; color:var(--muted); font-size:0.9rem;">No problem — come back and update this once you're placed. All the best!</p>

      <form method="post" action="{{ url_for('frontend.candidate_report_placement') }}" class="full-form" id="es-placement-form" style="display:none;">
        <div class="form-grid">
          <label>Employer Name <span style="color:#dc2626;">*</span><input type="text" name="employer_name" required></label>
          <label>Job Role <span style="color:#dc2626;">*</span><input type="text" name="job_role" required></label>
          <label>Joining Date <span style="color:#dc2626;">*</span><input type="date" name="joining_date" required></label>
          <label>Location<input type="text" name="location"></label>
          <label>Monthly Salary <span style="font-weight:normal; font-size:0.78rem; color:var(--muted);">(optional — you can add this later)</span><input type="text" name="salary" placeholder="e.g. 25000"></label>
        </div>
        <div class="form-actions">
          <button type="submit" class="primary-btn">Submit Placement Details</button>
        </div>
      </form>
    </div>

    <script>
    document.addEventListener('DOMContentLoaded', function () {
      var yesBtn = document.getElementById('es-yes-btn');
      var noBtn = document.getElementById('es-no-btn');
      var form = document.getElementById('es-placement-form');
      var noMsg = document.getElementById('es-no-message');
      var toggleBtns = document.getElementById('es-toggle-buttons');
      if (yesBtn) {
        yesBtn.addEventListener('click', function () {
          form.style.display = 'block';
          toggleBtns.style.display = 'none';
        });
      }
      if (noBtn) {
        noBtn.addEventListener('click', function () {
          noMsg.style.display = 'block';
          toggleBtns.style.display = 'none';
        });
      }
    });
    </script>
    {% endif %}

    {% if candidate.employer_name %}
    <div class="panel-card" id="feedback-card">
      {% if existing_feedback %}
        <h3>{{ _('feedback_prompt_title') }}</h3>
        <p>{{ _('feedback_already_submitted') }}</p>
        <div class="fb-stars-display">
          {% for i in range(1, 6) %}
            <span class="fb-star {{ 'filled' if i <= existing_feedback.rating }}">★</span>
          {% endfor %}
        </div>
        {% if existing_feedback.comment %}<p class="fb-comment">"{{ existing_feedback.comment }}"</p>{% endif %}
      {% else %}
        <h3>{{ _('feedback_prompt_title') }}</h3>
        <p>{{ _('feedback_prompt_body') }}</p>
        <form method="post" action="{{ url_for('frontend.candidate_feedback_submit') }}">
          <label>{{ _('feedback_rating_label') }}</label>
          <div class="fb-star-input" id="fb-star-input">
            {% for i in range(1, 6) %}
            <span class="fb-star" data-value="{{ i }}">★</span>
            {% endfor %}
          </div>
          <input type="hidden" name="rating" id="fb-rating-value" required>
          <label>{{ _('feedback_comment_label') }}
            <textarea name="comment" rows="3"></textarea>
          </label>
          <button type="submit" class="primary-btn">{{ _('feedback_submit') }}</button>
        </form>
      {% endif %}
    </div>

    <style>
      .fb-star-input, .fb-stars-display { display: flex; gap: 6px; font-size: 1.8rem; margin: 10px 0; }
      .fb-star-input .fb-star { cursor: pointer; color: var(--border); transition: color 0.15s ease; }
      .fb-star-input .fb-star.hover, .fb-star-input .fb-star.selected { color: #f59e0b; }
      .fb-stars-display .fb-star { color: var(--border); }
      .fb-stars-display .fb-star.filled { color: #f59e0b; }
      .fb-comment { color: var(--muted); font-style: italic; margin-top: 8px; }
    </style>

    <script>
    document.addEventListener('DOMContentLoaded', function () {
      const container = document.getElementById('fb-star-input');
      if (!container) return;
      const stars = Array.from(container.querySelectorAll('.fb-star'));
      const hiddenInput = document.getElementById('fb-rating-value');
      function setSelected(value) {
        stars.forEach(s => s.classList.toggle('selected', parseInt(s.dataset.value, 10) <= value));
      }
      stars.forEach(star => {
        star.addEventListener('mouseenter', () => {
          const value = parseInt(star.dataset.value, 10);
          stars.forEach(s => s.classList.toggle('hover', parseInt(s.dataset.value, 10) <= value));
        });
        star.addEventListener('mouseleave', () => stars.forEach(s => s.classList.remove('hover')));
        star.addEventListener('click', () => {
          hiddenInput.value = star.dataset.value;
          setSelected(parseInt(star.dataset.value, 10));
        });
      });
    });
    </script>
    {% endif %}

    {% if candidate.employer_name %}
    <div class="panel-card" id="timeline-card">
      <h3>{{ _('placement_timeline_title') }}</h3>
      <p style="color:var(--muted); font-size:0.85rem; margin-top:-6px; margin-bottom:14px;">{{ _('placement_timeline_subtitle') }}</p>
      <div class="pt-timeline">
        {% for cp in checkpoints %}
        <div class="pt-timeline-item pt-status-{{ cp.status }}">
          <div class="pt-dot"></div>
          <div>
            <div class="pt-label">{{ cp.label }}</div>
            <div class="pt-meta">
              {{ _('checkpoint_due_label') }} {{ cp.due_date.strftime('%d-%m-%Y') if cp.due_date else '-' }}
              &middot;
              <span class="pt-status-badge">
                {% if cp.status == 'completed' %}{{ _('checkpoint_status_completed') }}
                {% elif cp.status == 'missed' %}{{ _('checkpoint_status_missed') }}
                {% else %}{{ _('checkpoint_status_pending') }}{% endif %}
              </span>
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>

    <style>
      .pt-timeline { display: flex; flex-direction: column; gap: 4px; }
      .pt-timeline-item { display: flex; gap: 12px; padding: 10px 4px; border-bottom: 1px solid var(--border); }
      .pt-timeline-item:last-child { border-bottom: none; }
      .pt-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; background: #d1d5db; }
      .pt-status-completed .pt-dot { background: #16a34a; }
      .pt-status-missed .pt-dot { background: #dc2626; }
      .pt-status-pending .pt-dot { background: #f59e0b; }
      .pt-label { font-weight: 600; color: var(--text); }
      .pt-meta { font-size: 0.82rem; color: var(--muted); margin-top: 2px; }
      .pt-status-badge { font-weight: 600; }
      .pt-status-completed .pt-status-badge { color: #16a34a; }
      .pt-status-missed .pt-status-badge { color: #dc2626; }
      .pt-status-pending .pt-status-badge { color: #d97706; }
    </style>

    <div class="panel-card">
      <h3>{{ _('upload_proof_title') }}</h3>
      <p style="color:var(--muted); font-size:0.85rem; margin-top:-6px; margin-bottom:12px;">{{ _('upload_proof_body') }}</p>
      {% if candidate.placement_proof_uploaded %}
      <p style="color:#16a34a; font-size:0.88rem; margin-bottom:12px;">&#10003; {{ _('proof_already_uploaded') }}</p>
      {% endif %}
      <form method="post" action="{{ url_for('frontend.candidate_upload_proof') }}" enctype="multipart/form-data" class="full-form">
        <label>{{ _('upload_proof_choose_file') }}
          <input type="file" name="placement_proof" accept=".pdf,.jpg,.jpeg,.png" required>
        </label>
        <div class="form-actions">
          <button type="submit" class="primary-btn">{{ _('upload_proof_button') }}</button>
        </div>
      </form>
    </div>
    {% endif %}

    <div class="panel-card">
      <h3>{{ _('change_password') }}</h3>
      <form method="post" action="{{ url_for('frontend.candidate_change_password') }}" class="full-form">
        <div class="form-grid">
          <label>{{ _('current_password') }}<input type="password" name="current_password" required></label>
          <label>{{ _('new_password') }}<input type="password" name="new_password" required minlength="6"></label>
          <label>{{ _('confirm_new_password') }}<input type="password" name="confirm_password" required minlength="6"></label>
        </div>
        <div class="form-actions">
          <button type="submit" class="primary-btn">{{ _('change_password') }}</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
'''


def patch_frontend_py():
    if not os.path.exists(FRONTEND_PY_PATH):
        print(f"[SKIP] Could not find {FRONTEND_PY_PATH}. Run this script from the project root.")
        return

    with open(FRONTEND_PY_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "def candidate_report_placement" in content:
        print("[SKIP] frontend.py already has candidate_report_placement route. Nothing to do.")
        return

    if FRONTEND_ANCHOR not in content:
        print("[ERROR] Could not find the expected anchor text in frontend.py.")
        print("        The file may have changed since this script was written.")
        print("        No changes were made to frontend.py.")
        return

    content = content.replace(FRONTEND_ANCHOR, FRONTEND_NEW_BLOCK, 1)

    with open(FRONTEND_PY_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("[OK] Added candidate_report_placement route to frontend.py")


def patch_dashboard_html():
    if not os.path.exists(DASHBOARD_HTML_PATH):
        print(f"[SKIP] Could not find {DASHBOARD_HTML_PATH}. Run this script from the project root.")
        return

    with open(DASHBOARD_HTML_PATH, "r", encoding="utf-8") as f:
        existing = f.read()

    if "employment-status-card" in existing:
        print("[SKIP] dashboard.html already has the employment status section. Nothing to do.")
        return

    with open(DASHBOARD_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(DASHBOARD_HTML_FULL)

    print("[OK] Updated candidate/dashboard.html with the employment status section.")


if __name__ == "__main__":
    patch_frontend_py()
    patch_dashboard_html()
    print("Done.")
