"""SRS FR-16: runs due NotificationSchedule rows, resolves the target
candidates for each schedule's MessageTemplate.template_type, renders the
template body with per-candidate placeholders, and sends via
app.services.messaging_service (real for EMAIL, logged-only for other
channels - see that module's docstring).

Called hourly by app/services/scheduler.py. Each schedule's last_run_at is
checked so a daily/weekly/monthly schedule fires once per period even
though this runs every hour.

Custom cron schedules are NOT supported yet - croniter is not a project
dependency. They are skipped with a log line rather than silently ignored,
so this limitation is visible instead of hidden.
"""

import logging
from datetime import datetime

from app.extensions import db
from app.models.candidate import Candidate
from app.models.message_template import MessageTemplate
from app.models.notification_schedule import NotificationSchedule
from app.services.messaging_service import send_email

logger = logging.getLogger(__name__)


def _is_due(schedule, today):
    """True if this schedule should run today and has not already run
    today (or, for weekly/monthly, has not already run in the current
    period)."""
    if schedule.last_run_at and schedule.last_run_at.date() == today:
        return False

    if schedule.frequency == "daily":
        return True
    if schedule.frequency == "weekly":
        return schedule.day_of_week is not None and today.weekday() == schedule.day_of_week
    if schedule.frequency == "monthly":
        return schedule.day_of_month is not None and today.day == schedule.day_of_month
    if schedule.frequency == "custom":
        logger.warning(
            "notification_scheduler: schedule %s uses 'custom' frequency, which is not "
            "supported yet (croniter is not installed) - skipping.",
            schedule.id,
        )
        return False
    return False


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
        today = datetime.utcnow().date()
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


def run_notification_schedules():
    """Entry point called hourly by the scheduler. Returns a summary dict
    for logging - never raises, so one bad schedule/template does not stop
    the rest from running."""
    today = datetime.utcnow().date()
    schedules_run = 0
    emails_sent = 0
    skipped_channels = 0

    due_schedules = NotificationSchedule.query.filter_by(is_active=True).all()
    for schedule in due_schedules:
        try:
            if not _is_due(schedule, today):
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
                    if send_email(candidate.email, subject, body, candidate_id=candidate.id):
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
