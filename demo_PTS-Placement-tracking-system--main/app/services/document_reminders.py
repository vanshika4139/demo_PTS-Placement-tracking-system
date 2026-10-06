"""Post-placement reminder emails asking a candidate to upload their offer
letter / placement document.

Called hourly from app/services/scheduler.py. A candidate gets a reminder
REMINDER_DAYS days after joining_date while employer_name is set and
placement_proof_uploaded is still False, so uploading the proof stops them.
Only the latest due step is sent (no burst of 7+15+30), and only within
GRACE_DAYS of that step, so old candidates are not mass-emailed on go-live.
Sent steps are recorded in document_reminder_logs (one row per candidate/day).
"""

import logging
import os
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.candidate import Candidate
from app.models.document_reminder_log import DocumentReminderLog
from app.utils.email import send_notification_email

logger = logging.getLogger(__name__)

REMINDER_DAYS = [7, 15, 30]
GRACE_DAYS = 7


def _build_email(candidate, link):
    subject = "Please upload your offer letter / placement document"
    body = (
        f"Hello {candidate.full_name},\n\n"
        f"Congratulations on your placement at {candidate.employer_name}! "
        "We have not received your offer letter or placement document yet.\n\n"
        "Please log in and upload it from your dashboard:\n"
        f"{link}\n\n"
        "If you have already uploaded it, you can ignore this email.\n\n"
        "Thank you,\nCodevocado Placement Tracking"
    )
    return subject, body


def run_document_reminders(dry_run=False, now=None):
    base_url = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    if not base_url:
        logger.warning("document_reminders: APP_BASE_URL is not set - skipping (no valid link to send).")
        return {"error": "APP_BASE_URL not set"}

    now = now or datetime.utcnow()
    link = f"{base_url}/candidate/login"

    candidates = Candidate.query.filter(
        Candidate.is_deleted == False,
        Candidate.employer_name.isnot(None),
        Candidate.employer_name != "",
        Candidate.placement_proof_uploaded == False,
        Candidate.account_status == "active",
        Candidate.email.isnot(None),
        Candidate.email != "",
        Candidate.joining_date.isnot(None),
    ).all()

    sent_map = {}
    if candidates:
        rows = DocumentReminderLog.query.filter(
            DocumentReminderLog.candidate_id.in_([c.id for c in candidates])
        ).all()
        for r in rows:
            sent_map.setdefault(r.candidate_id, set()).add(r.reminder_day)

    result = {"checked": len(candidates), "sent": 0, "failed": 0, "would_send": []}

    for c in candidates:
        days = (now - c.joining_date).days
        due = [d for d in REMINDER_DAYS if days >= d]
        if not due:
            continue
        step = max(due)
        if days >= step + GRACE_DAYS:
            continue
        if step in sent_map.get(c.id, set()):
            continue

        if dry_run:
            result["would_send"].append(f"{c.full_name} <{c.email}> day {step}")
            continue

        subject, body = _build_email(c, link)
        try:
            send_notification_email(
                c.email, subject, body,
                organization_id=c.organization_id, candidate_id=c.id,
            )
        except Exception:
            logger.exception("document_reminders: send failed for candidate %s", c.id)
            result["failed"] += 1
            continue

        try:
            db.session.add(DocumentReminderLog(candidate_id=c.id, reminder_day=step))
            db.session.commit()
            result["sent"] += 1
        except IntegrityError:
            db.session.rollback()
        except Exception:
            db.session.rollback()
            logger.exception("document_reminders: could not record reminder for %s", c.id)

    return result
