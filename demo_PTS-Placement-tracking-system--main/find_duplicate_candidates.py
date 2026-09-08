"""
Finds duplicate candidates (by mobile, email, aadhaar, registration_number)
that were created before validation was added, and prints a report.

This script is READ-ONLY - it does not delete or modify anything.
Review the report, then manually decide which record to keep/edit/delete
via the app's Candidates page.

Usage:
    python find_duplicate_candidates.py
"""

from collections import defaultdict

from wsgi import app
from app.models import Candidate


def _find_duplicates(field_name):
    groups = defaultdict(list)
    candidates = Candidate.query.filter_by(is_deleted=False).all()
    for c in candidates:
        value = getattr(c, field_name)
        if value and str(value).strip():
            groups[str(value).strip()].append(c)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _print_report(title, duplicates):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")
    if not duplicates:
        print("  No duplicates found.")
        return
    for value, candidates in duplicates.items():
        print(f"\n  Value: {value}  ({len(candidates)} candidates)")
        for c in candidates:
            print(
                f"    - ID: {c.id} | Reg No: {c.registration_number or '-'} | "
                f"Name: {c.full_name} | Mobile: {c.mobile or '-'} | "
                f"Email: {c.email or '-'} | Aadhaar: {c.aadhaar or '-'} | "
                f"Created: {c.created_at.strftime('%d-%m-%Y') if c.created_at else '-'}"
            )


with app.app_context():
    print("Scanning for duplicate candidates...")

    mobile_dupes = _find_duplicates("mobile")
    email_dupes = _find_duplicates("email")
    aadhaar_dupes = _find_duplicates("aadhaar")
    reg_no_dupes = _find_duplicates("registration_number")

    _print_report("DUPLICATE MOBILE NUMBERS", mobile_dupes)
    _print_report("DUPLICATE EMAIL ADDRESSES", email_dupes)
    _print_report("DUPLICATE AADHAAR NUMBERS", aadhaar_dupes)
    _print_report("DUPLICATE REGISTRATION NUMBERS", reg_no_dupes)

    total_groups = len(mobile_dupes) + len(email_dupes) + len(aadhaar_dupes) + len(reg_no_dupes)
    print(f"\n{'=' * 70}")
    print(f"  Total duplicate groups found: {total_groups}")
    print(f"{'=' * 70}")
    print("\nNext step: review each group above, decide which record to keep,")
    print("then either edit or delete the extra ones from the Candidates page in the app.")