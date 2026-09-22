#!/usr/bin/env python3
"""
remove_dead_candidate_batch_scheme_code.py

Run from the project root (folder that contains `app\\` and `wsgi.py`):

    python remove_dead_candidate_batch_scheme_code.py

Sir's instruction: candidate / batch / scheme / placement no longer belong to
Super Admin at all (apply_superadmin_scope.py already blocked every route and
permission code for this). Because of that, every `if user.get("is_super_admin")`
/ `if not user.get("is_super_admin")` branch inside the candidate, batch and
scheme routes can never go the "super admin" way any more - it is dead code.
This script removes those branches and keeps only the org-user behaviour,
which is the one that always runs now.

This does NOT touch:
  - Reports (/reports) - still pending sir's decision on whether Super Admin
    keeps it.
  - Placement routes - checked, they don't have this dead pattern.
  - `show_creator_column = user.get("is_super_admin") or has_permission(...)`
    lines - harmless (an OR that's always resolved by has_permission now),
    left alone to keep this patch narrowly scoped.

Safe to run more than once. Backups: *.bak_before_deadcode
Nothing is written if a syntax check fails.
"""
import os
import sys

ROUTES_FILE = os.path.join("app", "routes", "frontend.py")
BACKUP_SUFFIX = ".bak_before_deadcode"


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def to_native(s, nl):
    return s.replace("\n", nl)


# Each patch: (label, old_text, new_text, expected_count)
# old_text / new_text are written with plain "\n" - converted to the file's
# actual line-ending style before matching/replacing.
PATCHES = [
    # ---------------- helper functions ----------------
    (
        "_scope_candidates_to_creator: drop dead is_super_admin branch",
        '    if not user or user.get("is_super_admin"):\n'
        "        return query\n"
        '    if has_permission(user, "candidate.view_all"):\n'
        "        return query\n"
        "    return query.filter(Candidate.created_by == user.get(\"id\"))",
        "    if not user:\n"
        "        return query\n"
        '    if has_permission(user, "candidate.view_all"):\n'
        "        return query\n"
        "    return query.filter(Candidate.created_by == user.get(\"id\"))",
        1,
    ),
    (
        "_can_access_candidate: drop dead is_super_admin branch",
        '    if not user or user.get("is_super_admin"):\n'
        "        return True\n"
        '    if has_permission(user, "candidate.view_all"):\n'
        "        return True\n"
        "    return candidate.created_by == user.get(\"id\")",
        "    if not user:\n"
        "        return True\n"
        '    if has_permission(user, "candidate.view_all"):\n'
        "        return True\n"
        "    return candidate.created_by == user.get(\"id\")",
        1,
    ),
    (
        "_scope_batches_to_creator: drop dead is_super_admin branch",
        '    if not user or user.get("is_super_admin"):\n'
        "        return query\n"
        '    if has_permission(user, "batch.view_all"):\n'
        "        return query\n"
        "    return query.filter(Batch.created_by == user.get(\"id\"))",
        "    if not user:\n"
        "        return query\n"
        '    if has_permission(user, "batch.view_all"):\n'
        "        return query\n"
        "    return query.filter(Batch.created_by == user.get(\"id\"))",
        1,
    ),
    (
        "_can_access_batch: drop dead is_super_admin branch",
        '    if not user or user.get("is_super_admin"):\n'
        "        return True\n"
        '    if has_permission(user, "batch.view_all"):\n'
        "        return True\n"
        "    return batch.created_by == user.get(\"id\")",
        "    if not user:\n"
        "        return True\n"
        '    if has_permission(user, "batch.view_all"):\n'
        "        return True\n"
        "    return batch.created_by == user.get(\"id\")",
        1,
    ),
    (
        "_scope_schemes_to_creator: drop dead is_super_admin branch",
        '    if not user or user.get("is_super_admin"):\n'
        "        return query\n"
        '    if has_permission(user, "scheme.view_all"):\n'
        "        return query\n"
        "    return query.filter(Scheme.created_by == user.get(\"id\"))",
        "    if not user:\n"
        "        return query\n"
        '    if has_permission(user, "scheme.view_all"):\n'
        "        return query\n"
        "    return query.filter(Scheme.created_by == user.get(\"id\"))",
        1,
    ),
    (
        "_can_access_scheme: drop dead is_super_admin branch",
        '    if not user or user.get("is_super_admin"):\n'
        "        return True\n"
        '    if has_permission(user, "scheme.view_all"):\n'
        "        return True\n"
        "    return scheme.created_by == user.get(\"id\")",
        "    if not user:\n"
        "        return True\n"
        '    if has_permission(user, "scheme.view_all"):\n'
        "        return True\n"
        "    return scheme.created_by == user.get(\"id\")",
        1,
    ),
    # ---------------- list routes ----------------
    (
        "organization_batches: always filter by own organization",
        "    query = Batch.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_batches_to_creator(query, user)\n"
        "    batches = query.order_by(Batch.created_at.desc()).all()",
        '    query = Batch.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_batches_to_creator(query, user)\n"
        "    batches = query.order_by(Batch.created_at.desc()).all()",
        1,
    ),
    (
        "organization_schemes: always filter by own organization",
        "    query = Scheme.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_schemes_to_creator(query, user)\n"
        "    schemes = query.order_by(Scheme.created_at.desc()).all()",
        '    query = Scheme.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_schemes_to_creator(query, user)\n"
        "    schemes = query.order_by(Scheme.created_at.desc()).all()",
        1,
    ),
    (
        "organization_candidates: always filter by own organization",
        "    query = Candidate.query.filter_by(is_deleted=False)\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "\n"
        "    if q:",
        '    query = Candidate.query.filter_by(is_deleted=False, organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "\n"
        "    if q:",
        1,
    ),
    (
        "organization_candidates_deleted: always filter by own organization",
        "    query = Candidate.query.filter_by(is_deleted=True)\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "    candidates = query.order_by(Candidate.updated_at.desc()).all()",
        '    query = Candidate.query.filter_by(is_deleted=True, organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "    candidates = query.order_by(Candidate.updated_at.desc()).all()",
        1,
    ),
    (
        "organization_candidates_bulk_action: always filter by own organization",
        "    query = Candidate.query.filter(Candidate.id.in_(candidate_ids))\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "    candidates = query.all()",
        "    query = Candidate.query.filter(\n"
        "        Candidate.id.in_(candidate_ids),\n"
        '        Candidate.organization_id == user.get("organization_id"),\n'
        "    )\n"
        "    query = _scope_candidates_to_creator(query, user)\n"
        "    candidates = query.all()",
        1,
    ),
    (
        "organization_candidates_export / export_pdf: always filter by own organization",
        "    query = Candidate.query.filter_by(is_deleted=False)\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "\n"
        '    search_query = request.args.get("q", "").strip()',
        '    query = Candidate.query.filter_by(is_deleted=False, organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "\n"
        '    search_query = request.args.get("q", "").strip()',
        2,
    ),
    (
        "organization_candidates_export_pdf: org_name no longer needs an is_super_admin lookup",
        '    org_name = "Codevocado Placement Tracking System"\n'
        '    if not user.get("is_super_admin"):\n'
        '        org = Organization.query.get(user.get("organization_id"))\n'
        "        if org:\n"
        "            org_name = org.organization_name",
        '    org_name = "Codevocado Placement Tracking System"\n'
        '    org = Organization.query.get(user.get("organization_id"))\n'
        "    if org:\n"
        "        org_name = org.organization_name",
        1,
    ),
    (
        "organization_candidates_bulk_set_passwords: always filter by own organization",
        "    query = Candidate.query.filter_by(is_deleted=False, password_hash=None)\n"
        '    if not user.get("is_super_admin"):\n'
        '        query = query.filter_by(organization_id=user.get("organization_id"))\n'
        "    query = _scope_candidates_to_creator(query, user)\n"
        "\n"
        "    candidates = query.all()",
        "    query = Candidate.query.filter_by(\n"
        "        is_deleted=False, password_hash=None, organization_id=user.get(\"organization_id\")\n"
        "    )\n"
        "    query = _scope_candidates_to_creator(query, user)\n"
        "\n"
        "    candidates = query.all()",
        1,
    ),
    # ---------------- create / edit routes ----------------
    (
        "organization_batch_create: organization is always the caller's own",
        '    user = session.get("user")\n'
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "\n"
        '    if request.method == "POST":\n'
        '        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")\n'
        "        if not org_id:\n"
        '            flash("Please select an organization", "error")\n'
        '            return render_template("organization/batches/form.html", batch=None, organizations=organizations)',
        '    user = session.get("user")\n'
        "    organizations = []\n"
        "\n"
        '    if request.method == "POST":\n'
        '        org_id = user.get("organization_id")\n'
        "        if not org_id:\n"
        '            flash("Please select an organization", "error")\n'
        '            return render_template("organization/batches/form.html", batch=None, organizations=organizations)',
        1,
    ),
    (
        "organization_batch_edit: organization is never reassigned by a non-super-admin caller",
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "\n"
        '    if request.method == "POST":\n'
        '        if user.get("is_super_admin"):\n'
        '            org_id = request.form.get("organization_id")\n'
        "            if org_id:\n"
        "                batch.organization_id = org_id\n"
        '        batch.name = request.form.get("name")',
        "    organizations = []\n"
        "\n"
        '    if request.method == "POST":\n'
        '        batch.name = request.form.get("name")',
        1,
    ),
    (
        "organization_scheme_create: organization is always the caller's own",
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "\n"
        '    if request.method == "POST":\n'
        '        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")\n'
        "        if not org_id:\n"
        '            flash("Please select an organization", "error")\n'
        '            return render_template("organization/schemes/form.html", scheme=None, organizations=organizations)',
        "    organizations = []\n"
        "\n"
        '    if request.method == "POST":\n'
        '        org_id = user.get("organization_id")\n'
        "        if not org_id:\n"
        '            flash("Please select an organization", "error")\n'
        '            return render_template("organization/schemes/form.html", scheme=None, organizations=organizations)',
        1,
    ),
    (
        "organization_scheme_edit: organization is never reassigned by a non-super-admin caller",
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "\n"
        '    if request.method == "POST":\n'
        '        if user.get("is_super_admin"):\n'
        '            org_id = request.form.get("organization_id")\n'
        "            if org_id:\n"
        "                scheme.organization_id = org_id\n"
        '        scheme.name = request.form.get("name")',
        "    organizations = []\n"
        "\n"
        '    if request.method == "POST":\n'
        '        scheme.name = request.form.get("name")',
        1,
    ),
    (
        "organization_candidate_create: batches/schemes/organization always scoped to caller's org",
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "\n"
        "    batch_query = Batch.query\n"
        "    scheme_query = Scheme.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))\n'
        '        scheme_query = scheme_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "    schemes = scheme_query.order_by(Scheme.name).all()\n"
        "\n"
        '    if request.method == "POST":\n'
        '        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")\n'
        "        if not org_id:\n"
        '            flash("Please select an organization", "error")\n'
        '            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)',
        "    organizations = []\n"
        "\n"
        '    batch_query = Batch.query.filter_by(organization_id=user.get("organization_id"))\n'
        '    scheme_query = Scheme.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "    schemes = scheme_query.order_by(Scheme.name).all()\n"
        "\n"
        '    if request.method == "POST":\n'
        '        org_id = user.get("organization_id")\n'
        "        if not org_id:\n"
        '            flash("Please select an organization", "error")\n'
        '            return render_template("organization/candidates/form.html", candidate=None, organizations=organizations, batches=batches, schemes=schemes)',
        1,
    ),
    (
        "organization_candidate_edit: batches/schemes/organization always scoped to caller's org",
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "\n"
        "    batch_query = Batch.query\n"
        "    scheme_query = Scheme.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))\n'
        '        scheme_query = scheme_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "    schemes = scheme_query.order_by(Scheme.name).all()\n"
        "\n"
        '    if request.method == "POST":\n'
        "        was_placed = bool(candidate.employer_name)",
        "    organizations = []\n"
        "\n"
        '    batch_query = Batch.query.filter_by(organization_id=user.get("organization_id"))\n'
        '    scheme_query = Scheme.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "    schemes = scheme_query.order_by(Scheme.name).all()\n"
        "\n"
        '    if request.method == "POST":\n'
        "        was_placed = bool(candidate.employer_name)",
        1,
    ),
    (
        "organization_candidate_edit: candidate's organization is never reassigned by a non-super-admin caller",
        '        if user.get("is_super_admin"):\n'
        '            org_id = request.form.get("organization_id")\n'
        "            if org_id:\n"
        "                candidate.organization_id = org_id\n"
        '        candidate.registration_number = request.form.get("registration_number") or None',
        '        candidate.registration_number = request.form.get("registration_number") or None',
        1,
    ),
    (
        "candidate_import: organization list is always empty (no super admin dropdown)",
        '    organizations = Organization.query.filter_by(status=1).all() if user.get("is_super_admin") else []\n'
        "    summary = None",
        "    organizations = []\n"
        "    summary = None",
        1,
    ),
    (
        "candidate_import: org_id is always the caller's own organization",
        '        org_id = request.form.get("organization_id") if user.get("is_super_admin") else user.get("organization_id")\n'
        '        file = request.files.get("csv_file")',
        '        org_id = user.get("organization_id")\n'
        '        file = request.files.get("csv_file")',
        1,
    ),
    # ---------------- tracking ----------------
    (
        "organization_tracking: candidates always filtered by own organization",
        "    candidate_query = Candidate.query.filter_by(is_deleted=False)\n"
        '    if not user.get("is_super_admin"):\n'
        '        candidate_query = candidate_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    candidate_query = _scope_candidates_to_creator(candidate_query, user)\n"
        "\n"
        "    if batch_filter:",
        '    candidate_query = Candidate.query.filter_by(is_deleted=False, organization_id=user.get("organization_id"))\n'
        "    candidate_query = _scope_candidates_to_creator(candidate_query, user)\n"
        "\n"
        "    if batch_filter:",
        1,
    ),
    (
        "organization_tracking: batches/schemes always filtered by own organization",
        "    batch_query = Batch.query\n"
        "    scheme_query = Scheme.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))\n'
        '        scheme_query = scheme_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "    schemes = scheme_query.order_by(Scheme.name).all()",
        '    batch_query = Batch.query.filter_by(organization_id=user.get("organization_id"))\n'
        '    scheme_query = Scheme.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "    schemes = scheme_query.order_by(Scheme.name).all()",
        1,
    ),
    (
        "organization_tracking: training centers list always filtered by own organization",
        "    training_center_query = Candidate.query.filter_by(is_deleted=False)\n"
        '    if not user.get("is_super_admin"):\n'
        '        training_center_query = training_center_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    training_center_query = _scope_candidates_to_creator(training_center_query, user)\n"
        "    training_centers = sorted(set(",
        '    training_center_query = Candidate.query.filter_by(is_deleted=False, organization_id=user.get("organization_id"))\n'
        "    training_center_query = _scope_candidates_to_creator(training_center_query, user)\n"
        "    training_centers = sorted(set(",
        1,
    ),
    # ---------------- attendance ----------------
    (
        "organization_attendance: batches always filtered by own organization",
        "    batch_query = Batch.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batch_query = _scope_batches_to_creator(batch_query, user)\n"
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "\n"
        '    selected_batch_id = request.args.get("batch_id", "").strip()\n'
        '    selected_date_str = request.args.get("date", "").strip()',
        '    batch_query = Batch.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batch_query = _scope_batches_to_creator(batch_query, user)\n"
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "\n"
        '    selected_batch_id = request.args.get("batch_id", "").strip()\n'
        '    selected_date_str = request.args.get("date", "").strip()',
        1,
    ),
    (
        "organization_attendance: invalid-batch check no longer references is_super_admin",
        '        if not batch or (not user.get("is_super_admin") and batch.organization_id != user.get("organization_id")) or not _can_access_batch(batch, user):\n'
        '            flash("Invalid batch selected.", "error")\n'
        '            return redirect(url_for("frontend.organization_attendance"))',
        '        if not batch or batch.organization_id != user.get("organization_id") or not _can_access_batch(batch, user):\n'
        '            flash("Invalid batch selected.", "error")\n'
        '            return redirect(url_for("frontend.organization_attendance"))',
        1,
    ),
    (
        "organization_attendance_mark: permission check no longer references is_super_admin",
        '    if not _can_access_batch(batch, user) or (not user.get("is_super_admin") and batch.organization_id != user.get("organization_id")):\n'
        '        flash("You do not have permission to mark attendance for this batch.", "error")\n'
        '        return redirect(url_for("frontend.organization_attendance"))',
        '    if not _can_access_batch(batch, user) or batch.organization_id != user.get("organization_id"):\n'
        '        flash("You do not have permission to mark attendance for this batch.", "error")\n'
        '        return redirect(url_for("frontend.organization_attendance"))',
        1,
    ),
    (
        "organization_attendance_report: batches always filtered by own organization",
        "    batch_query = Batch.query\n"
        '    if not user.get("is_super_admin"):\n'
        '        batch_query = batch_query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batch_query = _scope_batches_to_creator(batch_query, user)\n"
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "\n"
        '    selected_batch_id = request.args.get("batch_id", "").strip()\n'
        '    start_date_str = request.args.get("start_date", "").strip()',
        '    batch_query = Batch.query.filter_by(organization_id=user.get("organization_id"))\n'
        "    batch_query = _scope_batches_to_creator(batch_query, user)\n"
        "    batches = batch_query.order_by(Batch.name).all()\n"
        "\n"
        '    selected_batch_id = request.args.get("batch_id", "").strip()\n'
        '    start_date_str = request.args.get("start_date", "").strip()',
        1,
    ),
    (
        "organization_attendance_report: invalid-batch check no longer references is_super_admin",
        '        if not batch or (not user.get("is_super_admin") and batch.organization_id != user.get("organization_id")) or not _can_access_batch(batch, user):\n'
        '            flash("Invalid batch selected.", "error")\n'
        '            return redirect(url_for("frontend.organization_attendance_report"))',
        '        if not batch or batch.organization_id != user.get("organization_id") or not _can_access_batch(batch, user):\n'
        '            flash("Invalid batch selected.", "error")\n'
        '            return redirect(url_for("frontend.organization_attendance_report"))',
        1,
    ),
]


def fail(message):
    print(f"\nERROR: {message}\nNothing was changed.")
    sys.exit(1)


def main():
    if not os.path.exists(ROUTES_FILE):
        fail(f"{ROUTES_FILE} not found. Run this script from the project root (the folder that contains the `app` folder).")

    original = read_text(ROUTES_FILE)
    nl = newline_of(original)
    text = original

    done = []
    skipped = []

    for label, old, new, expected_count in PATCHES:
        old_native = to_native(old, nl)
        new_native = to_native(new, nl)

        if new_native in text and old_native not in text:
            skipped.append(f"{label} (already applied)")
            continue

        count = text.count(old_native)
        if count == 0:
            fail(f'Could not find the code for "{label}". The file may have already changed, or line endings differ from what this script expects.')
        if count != expected_count:
            fail(f'Expected to find the code for "{label}" {expected_count} time(s), found it {count} time(s). Stopping to avoid a wrong edit - the file may have been modified since this script was written.')

        text = text.replace(old_native, new_native)
        done.append(label)

    # Syntax check before writing anything.
    try:
        compile(text.replace("\r\n", "\n").lstrip("\ufeff"), ROUTES_FILE, "exec")
    except SyntaxError as exc:
        fail(f"The patched {ROUTES_FILE} would have a syntax error (line {exc.lineno}): {exc.msg}")

    if text != original:
        backup = ROUTES_FILE + BACKUP_SUFFIX
        if not os.path.exists(backup):
            write_text(backup, original)
            done.append(f"Backup saved to {backup}")
        write_text(ROUTES_FILE, text)

    print("\nDone:")
    for item in done:
        print(f"  + {item}")
    for item in skipped:
        print(f"  - skipped: {item}")
    print(f"\nTotal patches applied: {len([d for d in done if not d.startswith('Backup')])}")
    print("Next: restart `flask run`, then re-test the candidate/batch/scheme/attendance pages as an organization user.")


if __name__ == "__main__":
    main()