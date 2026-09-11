"""
Billing & subscription lifecycle logic - SRS FR-09 through FR-11.

Nothing here talks to a payment gateway directly (see
app/services/payment_gateway.py for that). This module owns the parts that
don't need one: generating invoice records on a schedule, nudging
organizations before they lapse, and suspending them if they do.

Everything is designed to be called from a single scheduled entrypoint
(scripts/run_billing_cycle.py) once a day, e.g. via cron / a container
sidecar / Celery beat - whatever this deployment already uses for the kind
of periodic job the platform doesn't have yet. Each function is also safe
to call individually (e.g. from a manual "Run now" button later) since none
of them assume they're only ever called once a day.
"""

import logging
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Invoice, Organization, Plan
from app.utils.email import send_notification_email

logger = logging.getLogger(__name__)

# How many days before expiry to send a renewal reminder. A list, not a
# single number, so an org gets nudged more than once (e.g. two weeks out,
# then three days out) rather than a single easy-to-miss email.
REMINDER_DAYS_BEFORE_EXPIRY = (14, 3)

# Organizations are auto-suspended this many days AFTER their subscription
# expiry date, not the instant it passes - gives a short grace window for
# a payment that's already in flight rather than an instant hard cutoff.
AUTO_SUSPEND_GRACE_DAYS = 3

_CYCLE_DAYS = {"monthly": 30, "quarterly": 90, "yearly": 365}


def _next_invoice_number():
    """Human-facing sequential-looking number. Not strictly gapless/atomic
    under heavy concurrency (fine for this app's scale - one billing job
    running once a day, not a high-throughput payment processor)."""
    year = datetime.utcnow().year
    count_this_year = Invoice.query.filter(
        Invoice.invoice_number.like(f"INV-{year}-%")
    ).count()
    return f"INV-{year}-{count_this_year + 1:06d}"


def generate_invoice_for_organization(organization, actor_id=None, is_prorated=False, proration_note=None, override_amount=None):
    """Creates one PENDING invoice for organization's current plan/cycle.
    Returns the created Invoice, or None if the organization has no plan
    (nothing to bill) or no subscription_expiry_date to anchor the period to.

    override_amount lets a prorated upgrade pass its own computed amount in
    instead of the plan's full price (see calculate_prorated_amount below).
    """
    if not organization.subscription_plan_id:
        return None

    plan = Plan.query.get(organization.subscription_plan_id)
    if plan is None:
        logger.warning("billing: organization %s has unknown plan_id %s", organization.id, organization.subscription_plan_id)
        return None

    cycle = organization.billing_cycle or plan.default_billing_cycle or "monthly"
    cycle_days = _CYCLE_DAYS.get(cycle, 30)

    period_end = organization.subscription_expiry_date or (datetime.utcnow() + timedelta(days=cycle_days))
    if hasattr(period_end, "date"):
        period_end = datetime.combine(period_end, datetime.min.time()) if not isinstance(period_end, datetime) else period_end
    period_start = period_end - timedelta(days=cycle_days)

    invoice = Invoice(
        invoice_number=_next_invoice_number(),
        organization_id=organization.id,
        plan_id=plan.id,
        billing_cycle=cycle,
        period_start=period_start,
        period_end=period_end,
        amount=override_amount if override_amount is not None else plan.price,
        is_prorated=1 if is_prorated else 0,
        proration_note=proration_note,
        status="PENDING",
        due_date=period_end,
        created_by=actor_id,
        modified_by=actor_id,
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def calculate_prorated_amount(old_plan, new_plan, subscription_expiry_date, billing_cycle="monthly"):
    """SRS FR-10: Prorated Plan Upgrade. Mid-cycle upgrade billed only for
    the days remaining in the current period, at the new plan's daily rate,
    credited for the unused portion of the old plan.

    Returns (amount, note) - amount can be 0 or negative-clamped-to-0 if the
    old plan was already more expensive per day than the new one (this
    function never returns a negative charge; a downgrade doesn't produce a
    refund here, it just costs 0 until the next full-cycle invoice).
    """
    cycle_days = _CYCLE_DAYS.get(billing_cycle, 30)

    if not subscription_expiry_date:
        days_remaining = cycle_days
    else:
        expiry = subscription_expiry_date
        if hasattr(expiry, "date") and not isinstance(expiry, datetime):
            expiry = datetime.combine(expiry, datetime.min.time())
        days_remaining = max(0, (expiry - datetime.utcnow()).days)
        days_remaining = min(days_remaining, cycle_days)  # never prorate more than one full cycle

    old_daily_rate = float(old_plan.price) / cycle_days if old_plan else 0
    new_daily_rate = float(new_plan.price) / cycle_days

    credit = old_daily_rate * days_remaining
    charge = new_daily_rate * days_remaining
    amount = max(0.0, round(charge - credit, 2))

    note = (
        f"Upgraded {old_plan.name if old_plan else 'no plan'} -> {new_plan.name}, "
        f"{days_remaining} day(s) remaining in current cycle"
    )
    return amount, note


def run_renewal_reminders(actor_id=None):
    """SRS FR-10: Renewal Reminders. Emails every active organization whose
    subscription_expiry_date is exactly REMINDER_DAYS_BEFORE_EXPIRY days out.
    Idempotent per day - won't re-send twice for the same threshold because
    it only matches organizations whose expiry is EXACTLY N days away today,
    not <= N, so this is safe to run more than once in a day if needed.
    """
    sent = 0
    today = datetime.utcnow().date()

    organizations = Organization.query.filter(
        Organization.is_deleted.is_(False),
        Organization.status == 1,
        Organization.subscription_expiry_date.isnot(None),
    ).all()

    for org in organizations:
        days_left = (org.subscription_expiry_date - today).days
        if days_left not in REMINDER_DAYS_BEFORE_EXPIRY:
            continue
        if not org.email:
            logger.warning("billing: organization %s has no email on file, skipping renewal reminder", org.id)
            continue

        try:
            send_notification_email(
                org.email,
                subject=f"Your Codevocado subscription expires in {days_left} day(s)",
                body=(
                    f"Hi {org.contact_person or org.organization_name},\n\n"
                    f"Your Codevocado subscription is set to expire on "
                    f"{org.subscription_expiry_date.strftime('%d-%m-%Y')} "
                    f"({days_left} day(s) from today). Please renew to avoid "
                    f"any interruption to your access.\n\n"
                    f"If you've already renewed, you can ignore this message."
                ),
            )
            sent += 1
        except Exception as exc:
            # Email failures (e.g. SMTP not configured) should never break
            # the rest of the billing cycle for other organizations.
            logger.warning("billing: renewal reminder email failed for org %s (%s)", org.id, exc)

    return sent


def run_auto_suspend(actor_id=None):
    """SRS FR-11: Auto-Suspend on Expiry. Suspends (status=0) every active
    organization whose subscription_expiry_date is more than
    AUTO_SUSPEND_GRACE_DAYS in the past. Data is retained - this only flips
    `status`, exactly like the existing manual "Suspend" button does, it
    never touches is_deleted or any candidate/user data.
    """
    suspended_ids = []
    cutoff = datetime.utcnow().date() - timedelta(days=AUTO_SUSPEND_GRACE_DAYS)

    overdue_orgs = Organization.query.filter(
        Organization.is_deleted.is_(False),
        Organization.status == 1,
        Organization.subscription_expiry_date.isnot(None),
        Organization.subscription_expiry_date < cutoff,
    ).all()

    for org in overdue_orgs:
        org.status = 0
        org.payment_status = "OVERDUE"
        # Note: Organization.modified_by is an integer column (unlike the
        # UUID-string modified_by used on Invoice/Plan/Role/Module elsewhere
        # in this codebase) and isn't set anywhere else in the app either,
        # so it's left untouched here rather than passing an incompatible
        # UUID actor_id into it (see the same fix in
        # app/services/payment_gateway.py's mark_invoice_paid).
        org.modified_at = datetime.utcnow()
        suspended_ids.append(org.id)
        logger.info("billing: auto-suspended organization %s (expired %s)", org.id, org.subscription_expiry_date)

    if suspended_ids:
        db.session.commit()

    return suspended_ids


def run_overdue_invoice_sweep():
    """Marks any PENDING invoice past its due_date as OVERDUE. Doesn't
    touch the organization's status directly - run_auto_suspend (above)
    is what actually suspends access, this just keeps invoice records
    accurate for the Subscription page and reports."""
    updated = 0
    overdue = Invoice.query.filter(
        Invoice.status == "PENDING",
        Invoice.due_date < datetime.utcnow(),
    ).all()
    for inv in overdue:
        inv.status = "OVERDUE"
        updated += 1
    if updated:
        db.session.commit()
    return updated


def run_billing_cycle(actor_id=None):
    """Single entrypoint that runs every step in order. Each step commits
    its own changes and is independently exception-safe internally where it
    matters (see run_renewal_reminders), but this wraps the whole call in a
    try/except per-step too so one broken step (e.g. a DB hiccup mid-way)
    doesn't prevent the others from running."""
    results = {"invoices_generated": 0, "reminders_sent": 0, "invoices_marked_overdue": 0, "organizations_suspended": []}

    try:
        due_for_invoice = Organization.query.filter(
            Organization.is_deleted.is_(False),
            Organization.status == 1,
            Organization.subscription_plan_id.isnot(None),
            Organization.subscription_expiry_date.isnot(None),
            Organization.subscription_expiry_date <= (datetime.utcnow().date() + timedelta(days=1)),
        ).all()
        for org in due_for_invoice:
            existing_open_invoice = Invoice.query.filter_by(
                organization_id=org.id, status="PENDING"
            ).filter(Invoice.period_end == org.subscription_expiry_date).first()
            if existing_open_invoice:
                continue
            invoice = generate_invoice_for_organization(org, actor_id=actor_id)
            if invoice:
                results["invoices_generated"] += 1
    except Exception:
        logger.exception("billing: invoice generation step failed")
        db.session.rollback()

    try:
        results["reminders_sent"] = run_renewal_reminders(actor_id=actor_id)
    except Exception:
        logger.exception("billing: renewal reminder step failed")
        db.session.rollback()

    try:
        results["invoices_marked_overdue"] = run_overdue_invoice_sweep()
    except Exception:
        logger.exception("billing: overdue invoice sweep failed")
        db.session.rollback()

    try:
        results["organizations_suspended"] = run_auto_suspend(actor_id=actor_id)
    except Exception:
        logger.exception("billing: auto-suspend step failed")
        db.session.rollback()

    return results