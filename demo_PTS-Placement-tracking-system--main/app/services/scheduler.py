"""
Daily billing scheduler - SRS FR-10 (Renewal Reminders) and FR-11
(Auto-Suspend on Expiry), plus the invoice-generation and overdue-sweep
steps that live alongside them in app/services/billing.py.

Before this module existed, run_billing_cycle() could only be triggered by
hand (scripts/run_billing_cycle.py, or the "Run Billing Cycle Now" button
on the Integrations page). This wires it to actually run once a day on its
own, using APScheduler's BackgroundScheduler - a scheduler thread living
inside the Flask process itself, so nothing extra needs to be installed or
configured at the OS level (no cron entry, no Windows Task Scheduler job).

Requires: pip install apscheduler

Wiring: call init_scheduler(app) exactly once, from create_app(), after
init_extensions(app) so the app + db are ready before the first job could
possibly fire. See app/__init__.py.
"""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = None  # module-level so a second init_scheduler() call is a no-op, not a duplicate scheduler


def init_scheduler(app, hour=2, minute=0):
    """Registers the daily billing-cycle job against `app`.

    hour/minute (24h, server local time) default to 02:00 - a quiet time
    picked with no real traffic data behind it; change it here if this
    deployment needs something else.

    Guards against Flask's debug auto-reloader, which runs the app in two
    processes (a monitor + a worker) and would otherwise register the job
    twice, firing every invoice/reminder/suspension twice a day. When
    app.debug is off, as in this deployment ("Debug mode: off" in the
    flask run log), there's only one process and this check is a no-op.
    """
    global _scheduler

    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    if _scheduler is not None:
        return

    from app.services.billing import run_billing_cycle

    def _run_daily_billing_cycle():
        with app.app_context():
            logger.info("scheduler: starting daily billing cycle")
            try:
                results = run_billing_cycle()
                logger.info("scheduler: daily billing cycle finished: %s", results)
            except Exception:
                # A failed run should never crash the scheduler thread -
                # it should just log and try again at the next scheduled time.
                logger.exception("scheduler: daily billing cycle failed")

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_daily_billing_cycle,
        trigger="cron",
        hour=hour,
        minute=minute,
        id="daily_billing_cycle",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("scheduler: daily billing cycle scheduled for %02d:%02d every day", hour, minute)
    