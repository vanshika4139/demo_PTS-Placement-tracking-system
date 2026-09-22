"""SRS FR-16: runs due NotificationSchedule rows, resolves the target
candidates for each schedule's MessageTemplate.template_type, renders the
template body with per-candidate placeholders, and sends via
app.services.messaging_service (real for EMAIL, logged-only for other
channels - see that module's docstring).

Called hourly by app/services/scheduler.py. Each schedule's last_run_at is
checked so a daily/weekly/monthly schedule fires once per period even
though this runs every hour.

Custom cron schedules (frequency="custom") are supported via the croniter
library - see _is_custom_cron_due() below. Unlike daily/weekly/monthly,
a custom cron expression can fire more than once a day, so it is evaluated
against the schedule's last_run_at timestamp rather than a once-per-day
date check.
"""

import logging
from datetime import datetime, timedelta

from croniter import croniter

from app.extensions import db
from app.models.candidate import Candidate
from app.models.message_template import MessageTemplate
from app.models.notification_schedule import NotificationSchedule
from app.services.messaging_service import send_email

logger = logging.getLogger(__name__)


def _is_due(schedule, today, force=False, now=None):
    """True if this schedule should run today and has not already run
    today (or, for weekly/monthly, has not already run in the current
    period). If force=True, skips the already-ran-today check (used by
    the manual 'Run Now' button for testing/demo).

    Custom cron schedules bypass the once-per-day guard entirely (see
    _is_custom_cron_due) since a cron expression can legitimately fire
    more than once a day (e.g. every 6 hours) - the date-based guard
    below only makes sense for daily/weekly/monthly."""
    if now is None:
        now = datetime.utcnow()

    if schedule.frequency == "custom":
        return _is_custom_cron_due(schedule, now, force=force)

    if not force and schedule.last_run_at and schedule.last_run_at.date() == today:
        return False

    if schedule.frequency == "daily":
        return True
    if schedule.frequency == "weekly":
        return schedule.day_of_week is not None and today.weekday() == schedule.day_of_week
    if schedule.frequency == "monthly":
        return schedule.day_of_month is not None and today.day == schedule.day_of_month
    return False


def _is_custom_cron_due(schedule, now, force=False):
    """Evaluates a custom cron expression (e.g. '0 */6 * * *') using
    croniter. Anchors from the schedule's last_run_at - if the cron's
    next scheduled fire time after that anchor has already passed (i.e.
    is <= now), the schedule is due. A schedule that has never run yet
    anchors from one hour ago, matching this job's hourly polling
    interval, so a newly created custom schedule can fire on its very
    first eligible tick instead of waiting a full extra cycle."""
    expression = (schedule.custom_cron_expression or "").strip()
    if not expression:
        logger.warning(
            "notification_scheduler: schedule %s has frequency='custom' but no cron "
            "expression saved - skipping.",
            schedule.id,
        )
        return False

    if not croniter.is_valid(expression):
        logger.warning(
            "notification_scheduler: schedule %s has an invalid cron expression '%s' - skipping.",
            schedule.id, expression,
        )
        return False

    if force:
        return True

    base_time = schedule.last_run_at or (now - timedelta(hours=1))
    next_fire_time = croniter(expression, base_time).get_next(datetime)
    return next_fire_time <= now


def _candidates_for_template_type(template_type):
    """Resolves which candidates a given template type should go to.
    See app/services/notification_scheduler.py module docstring for the
    overall design; this mapping is intentionally simple and can be
    refined per-template later without touching the scheduling logic above."""
    base = Candidate.query.filter_by(is_deleted=False)

    if template_type == "PLACEMENT_REMINDER":
        return base.filter(
            (Candidate.employer_name.is_(None)) | (Candidate.employer_name == "")
        ).all()
    if template_type == "VERIFICATION_REQUEST":
        return base.filter(
            (Candidate.verification_status.is_(None)) | (Candidate.verification_status == "pending")
        ).all()
    if template_type == "ANNIVERSARY":
        now = datetime.utcnow()
        today = now.date()
        return [
            c for c in base.filter(Candidate.joining_date.isnot(None)).all()
            if c.joining_date.month == today.month and c.joining_date.day == today.day
        ]
    # SALARY_UPDATE, SURVEY, OFFER_LETTER - all active placed candidates
    return base.filter(
        Candidate.employer_name.isnot(None),
        Candidate.employer_name != "",
        Candidate.account_status == "active",
    ).all()


def _render(body, candidate):
    """Fills {candidate_name}/{employer_name}/{joining_date} placeholders.
    Missing values render as an empty string rather than raising, so a
    template referencing {employer_name} still sends to a candidate who
    has none yet."""
    return body.format(
        candidate_name=candidate.full_name or "",
        employer_name=candidate.employer_name or "",
        joining_date=candidate.joining_date.strftime("%d-%m-%Y") if candidate.joining_date else "",
    )


def run_notification_schedules(force=False):
    """Entry point called hourly by the scheduler. Returns a summary dict
    for logging - never raises, so one bad schedule/template does not stop
    the rest from running. force=True (used by the manual 'Run Now'
    button) bypasses the once-per-day/period check in _is_due()."""
    now = datetime.utcnow()
    today = now.date()
    schedules_run = 0
    emails_sent = 0
    skipped_channels = 0

    due_schedules = NotificationSchedule.query.filter_by(is_active=True).all()
    for schedule in due_schedules:
        try:
            if not _is_due(schedule, today, force=force, now=now):
                continue

            template = MessageTemplate.query.get(schedule.template_id)
            if not template or not template.is_active:
                continue

            candidates = _candidates_for_template_type(template.template_type)

            if template.channel == "EMAIL":
                for candidate in candidates:
                    if not candidate.email:
                        continue
                    subject = _render(template.subject or template.template_type.replace("_", " ").title(), candidate)
                    body = _render(template.body, candidate)
                    if send_email(candidate.email, subject, body, organization_id=candidate.organization_id, candidate_id=candidate.id):
                        emails_sent += 1
            else:
                # WHATSAPP/SMS/VOICE_CALL/PUSH have no real provider configured
                # yet - see app/services/messaging_service.py. Not attempting
                # to send avoids pretending this schedule did something it
                # did not; the dashboard channel-delivered counts stay honest.
                logger.info(
                    "notification_scheduler: schedule %s uses channel %s, which has no "
                    "real provider configured yet - skipping send for %d candidate(s).",
                    schedule.id, template.channel, len(candidates),
                )
                skipped_channels += 1

            schedule.last_run_at = datetime.utcnow()
            db.session.commit()
            schedules_run += 1
        except Exception:
            db.session.rollback()
            logger.exception("notification_scheduler: schedule %s failed", schedule.id)

    return {
        "schedules_run": schedules_run,
        "emails_sent": emails_sent,
        "skipped_channels": skipped_channels,
    }
