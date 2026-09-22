#!/usr/bin/env python3
"""
apply_superadmin_scope.py

Run from the project root (folder that contains `app\\` and `wsgi.py`):

    python apply_superadmin_scope.py

Sir's rule: Super Admin only deals with organizations, plans and KYC - nothing
at candidate level. Re-reading the code showed four places where that was not
fully true yet:

  1. app/utils/permissions.py - the list of "organization-only" permissions was
     missing the codes the routes really use for candidate edit / export /
     restore / bulk actions, batch and scheme edit, placement updates,
     marking attendance and the organization dashboard. Because of that a
     Super Admin could still open or POST to those pages by typing the URL.
     They are added to the list now.
  2. frontend.py - _send_placement_email() also emailed every Super Admin
     whenever a candidate got placed. Candidate-level news now goes only to
     the organization's own users.
  3. frontend.py + users/form.html - when the Super Admin creates or edits a
     user, the Role dropdown listed every organization's custom roles. A role
     created by one organization could be given to another organization's
     user. The dropdown now shows only global roles + the chosen
     organization's own roles, and the server refuses any other combination.
  4. Roles & Permissions page (Super Admin) - organization-created roles now
     show the organization's name next to the role name, so two "Center
     Incharge" roles from different organizations can be told apart.

Safe to run more than once. Backups: *.bak_before_scope
Nothing is written if a syntax check fails.
"""
import os
import re
import sys

PERMISSIONS_FILE = os.path.join("app", "utils", "permissions.py")
ROUTES_FILE = os.path.join("app", "routes", "frontend.py")
USERS_FORM = os.path.join("app", "templates", "super_admin", "users", "form.html")
ROLES_TEMPLATE = os.path.join("app", "templates", "super_admin", "roles_permissions.html")
BACKUP_SUFFIX = ".bak_before_scope"

# ---------------------------------------------------------------- permissions.py
PERMISSIONS_PATCH = (
    "permissions.py: Super Admin blocked from the remaining candidate-level permissions",
    re.compile(r'"candidate\.update", "candidate\.export"'),
    re.compile(r'(        "attendance\.view", "attendance\.edit",\r?\n)(    \})'),
    lambda m, nl: (
        m.group(1)
        + "        # Codes the routes really use for update / export / restore / view-all /" + nl
        + "        # marking attendance / the organization dashboard. They were missing here," + nl
        + "        # so Super Admin could still reach those candidate-level pages." + nl
        + '        "candidate.update", "candidate.export", "candidate.view_deleted", "candidate.view_all",' + nl
        + '        "batch.update", "batch.view_all",' + nl
        + '        "scheme.update", "scheme.view_all",' + nl
        + '        "placement.update", "attendance.mark", "dashboard.view",' + nl
        + m.group(2)
    ),
)


# ---------------------------------------------------------------- frontend.py
def _role_check_block(render_call, nl):
    lines = [
        "        # A role that belongs to one organization can only be given to users of that",
        "        # same organization (global roles can be given to anyone).",
        '        if role != "super_admin":',
        "            chosen_role = Role.query.get(rbac_role_id)",
        "            if chosen_role is None or chosen_role.is_deleted or (",
        "                chosen_role.organization_id is not None",
        "                and chosen_role.organization_id != _parse_int(organization_id)",
        "            ):",
        '                flash("That role belongs to a different organization. Please pick a role for this organization.", "error")',
        f"                {render_call}",
    ]
    return nl.join(lines) + nl


CREATE_RENDER = 'return render_template("super_admin/users/form.html", user=None, organizations=organizations, roles=roles)'
EDIT_RENDER = 'return render_template("super_admin/users/form.html", user=user, organizations=organizations, roles=roles, current_role_id=current_role_id)'

ROUTE_PATCHES = [
    (
        "frontend.py: placement emails no longer go to Super Admin",
        re.compile(r"(?m)^            User\.organization_id == candidate\.organization_id,"),
        re.compile(r"\(User\.organization_id == candidate\.organization_id\) \| \(User\.is_super_admin == True\),"),
        lambda m, nl: "User.organization_id == candidate.organization_id,  # Super Admin does not deal with candidates",
    ),
    (
        "frontend.py: Add User refuses another organization's role",
        re.compile(
            r'different organization\. Please pick a role for this organization\.", "error"\)\r?\n'
            r'                return render_template\("super_admin/users/form\.html", user=None'
        ),
        re.compile(
            r'(        if role != "super_admin" and not rbac_role_id:\r?\n'
            r'            flash\("Please select a role \(Trainer, Recruiter, etc\.\) for this user\.", "error"\)\r?\n'
            r'            return render_template\("super_admin/users/form\.html", user=None, organizations=organizations, roles=roles\)\r?\n)'
        ),
        lambda m, nl: m.group(1) + nl + _role_check_block(CREATE_RENDER, nl),
    ),
    (
        "frontend.py: Edit User refuses another organization's role",
        re.compile(
            r'different organization\. Please pick a role for this organization\.", "error"\)\r?\n'
            r'                return render_template\("super_admin/users/form\.html", user=user'
        ),
        re.compile(
            r'(        if role != "super_admin" and not rbac_role_id:\r?\n'
            r'            flash\("Please select a role \(Trainer, Recruiter, etc\.\) for this user\.", "error"\)\r?\n'
            r'            return render_template\("super_admin/users/form\.html", user=user, organizations=organizations, roles=roles, current_role_id=current_role_id\)\r?\n)'
        ),
        lambda m, nl: m.group(1) + nl + _role_check_block(EDIT_RENDER, nl),
    ),
    (
        "frontend.py: Roles & Permissions page knows each role's organization name",
        re.compile(r"org_name_by_id=org_name_by_id"),
        re.compile(
            r'(    return render_template\(\r?\n'
            r'        "super_admin/roles_permissions\.html",\r?\n'
            r'        roles=roles,\r?\n)'
        ),
        lambda m, nl: (
            "    org_ids_with_roles = {r.organization_id for r in roles if r.organization_id}" + nl
            + "    org_name_by_id = (" + nl
            + "        {o.id: o.organization_name for o in Organization.query.filter(Organization.id.in_(org_ids_with_roles)).all()}" + nl
            + "        if org_ids_with_roles else {}" + nl
            + "    )" + nl + nl
            + m.group(1)
            + "        org_name_by_id=org_name_by_id," + nl
        ),
    ),
]

# ---------------------------------------------------------------- templates
FORM_PATCHES = [
    (
        "users/form.html: role options carry their organization",
        re.compile(r'data-org="'),
        re.compile(r'<option value="\{\{ r\.id \}\}" \{\{ \'selected\' if current_role_id == r\.id \}\}>'),
        lambda m, nl: '<option value="{{ r.id }}" data-org="{{ r.organization_id or \'\' }}" {{ \'selected\' if current_role_id == r.id }}>',
    ),
    (
        "users/form.html: organization dropdown re-filters the roles",
        re.compile(r'<select name="organization_id" onchange="filterRoles\(\)">'),
        re.compile(r'<select name="organization_id">'),
        lambda m, nl: '<select name="organization_id" onchange="filterRoles()">',
    ),
    (
        "users/form.html: script that shows only the right roles",
        re.compile(r"function filterRoles\(\)"),
        re.compile(r"window\.onload = toggleOrgField;"),
        lambda m, nl: nl.join([
            "// Show only global roles + the chosen organization's own roles.",
            "function filterRoles() {",
            "  const orgSelect = document.querySelector('select[name=\"organization_id\"]');",
            "  const roleSelect = document.querySelector('select[name=\"rbac_role_id\"]');",
            "  if (!orgSelect || !roleSelect) return;",
            "  const org = orgSelect.value;",
            "  Array.from(roleSelect.options).forEach(function (opt) {",
            "    if (!opt.value) return;",
            "    const roleOrg = opt.dataset.org || '';",
            "    const allowed = roleOrg === '' || roleOrg === org;",
            "    opt.hidden = !allowed;",
            "    opt.disabled = !allowed;",
            "  });",
            "  if (roleSelect.selectedOptions.length && roleSelect.selectedOptions[0].disabled) {",
            "    roleSelect.value = '';",
            "  }",
            "}",
            "window.onload = function () { toggleOrgField(); filterRoles(); };",
        ]),
    ),
]

ROLES_TEMPLATE_PATCH = (
    "roles_permissions.html: organization name next to organization-created roles",
    re.compile(r"org_name_by_id"),
    re.compile(r"\{\{ role\.name \}\}"),
    lambda m, nl: (
        "{{ role.name }}{% if role.organization_id %} "
        "<small style=\"opacity:.7\">({{ org_name_by_id.get(role.organization_id, 'org ' ~ role.organization_id) }})</small>"
        "{% endif %}"
    ),
)


# ---------------------------------------------------------------- helpers
def fail(message):
    print(f"\nERROR: {message}\nNothing was changed.")
    sys.exit(1)


def read_text(path):
    # newline="" keeps the file's existing line endings (Windows CRLF) intact.
    # A leading BOM is kept as-is and written back unchanged.
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def apply_small(text, patches, nl, done, skipped):
    for label, marker_re, anchor_re, build in patches:
        if marker_re.search(text):
            skipped.append(f"{label} (already applied)")
            continue
        found = anchor_re.findall(text)
        if len(found) != 1:
            fail(f'Could not find the code for "{label}" exactly once (found {len(found)}). The file may have been edited.')
        text = anchor_re.sub(lambda m, b=build: b(m, nl), text, count=1)
        done.append(label)
    return text


def main():
    files = (PERMISSIONS_FILE, ROUTES_FILE, USERS_FORM, ROLES_TEMPLATE)
    for path in files:
        if not os.path.exists(path):
            fail(f"{path} not found. Run this script from the project root (the folder that contains the `app` folder).")

    originals = {path: read_text(path) for path in files}
    patched = dict(originals)
    done, skipped = [], []

    patched[PERMISSIONS_FILE] = apply_small(
        patched[PERMISSIONS_FILE], [PERMISSIONS_PATCH], newline_of(originals[PERMISSIONS_FILE]), done, skipped
    )
    patched[ROUTES_FILE] = apply_small(
        patched[ROUTES_FILE], ROUTE_PATCHES, newline_of(originals[ROUTES_FILE]), done, skipped
    )
    patched[USERS_FORM] = apply_small(
        patched[USERS_FORM], FORM_PATCHES, newline_of(originals[USERS_FORM]), done, skipped
    )
    patched[ROLES_TEMPLATE] = apply_small(
        patched[ROLES_TEMPLATE], [ROLES_TEMPLATE_PATCH], newline_of(originals[ROLES_TEMPLATE]), done, skipped
    )

    for path in (PERMISSIONS_FILE, ROUTES_FILE):
        try:
            compile(patched[path].replace("\r\n", "\n").lstrip("\ufeff"), path, "exec")
        except SyntaxError as exc:
            fail(f"The patched {path} would have a syntax error (line {exc.lineno}): {exc.msg}")

    for path in files:
        if patched[path] != originals[path]:
            backup = path + BACKUP_SUFFIX
            if not os.path.exists(backup):
                write_text(backup, originals[path])
                done.append(f"Backup saved to {backup}")
            write_text(path, patched[path])

    print("\nDone:")
    for item in done:
        print(f"  + {item}")
    for item in skipped:
        print(f"  - skipped: {item}")
    print("\nNext: restart `flask run`.")


if __name__ == "__main__":
    main()
    