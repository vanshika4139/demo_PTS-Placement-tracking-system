"""
Run once a day (e.g. via cron: `0 3 * * * cd /path/to/app && python scripts/run_billing_cycle.py`)
or however this deployment already schedules periodic jobs.

Drives all of SRS FR-10/FR-11 in one pass:
  - generates invoices for organizations approaching their renewal date
  - sends renewal reminder emails (14 days and 3 days out)
  - marks any invoice past its due date as OVERDUE
  - auto-suspends organizations whose subscription expired more than
    AUTO_SUSPEND_GRACE_DAYS days ago

Safe to run more than once in a day - see billing.py docstrings for why
each step is idempotent.
"""

from wsgi import app
from app.services.billing import run_billing_cycle

with app.app_context():
    results = run_billing_cycle()
    print(
        f"Billing cycle complete: "
        f"{results['invoices_generated']} invoice(s) generated, "
        f"{results['reminders_sent']} reminder(s) sent, "
        f"{results['invoices_marked_overdue']} invoice(s) marked overdue, "
        f"{len(results['organizations_suspended'])} organization(s) auto-suspended "
        f"{results['organizations_suspended'] or ''}"
    )