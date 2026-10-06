"""Post-placement reminder emails asking a candidate to upload the documents
Super Admin marked as required (offer letter, joining letter, salary slip).

Called hourly from app/services/scheduler.py. Settings live in
platform_settings (doc_require_*, doc_reminder_days). A candidate gets ONE
email, doc_reminder_days days after joining_date, listing only the required
documents still missing. Nothing missing means no email.
Only sent within GRACE_DAYS of that day, so old candidates are not
mass-emailed on go-live. Sent reminders are recorded in
document_reminder_logs (one row per candidate/day value).
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

DEFAULT_REMINDER_DAY = 30
GRACE_DAYS = 7


def _missing_documents(c, s):
    missing = []
    if s.doc_require_offer_letter and not c.placement_proof_uploaded:
        missing.append("Offer letter / placement document")
    if s.doc_require_joining_letter and not c.joining_letter_path:
        missing.append("Joining letter")
    if s.doc_require_salary_slip and not c.salary_slip_path:
        missing.append("Salary slip")
    return missing


def _build_email(candidate, link, missing):
    subject = "Please upload your placement documents"
    items = "\n".join(f"- {m}" for m in missing)
    body = (
        f"Hello {candidate.full_name},\n\n"
        f"Congratulations on your placement at {candidate.employer_name}! "
        "We have not received the following document(s) yet:\n\n"
        f"{items}\n\n"
        "Please log in and upload them from your dashboard:\n"
        f"{link}\n\n"
        "If you have already uploaded them, you can ignore this email.\n\n"
        "Thank you,\nCodevocado Placement Tracking"
    )
    return subject, body


def run_document_reminders(dry_run=False, now=None):
    base_url = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    if not base_url:
        logger.warning("document_reminders: APP_BASE_URL is not set - skipping (no valid link to send).")
        return {"error": "APP_BASE_URL not set"}

    from app.utils.platform_settings import get_platform_settings
    settings = get_platform_settings()
    step = settings.doc_reminder_days or DEFAULT_REMINDER_DAY

    now = now or datetime.utcnow()
    link = f"{base_url}/candidate/login"

    candidates = Candidate.query.filter(
        Candidate.is_deleted == False,
        Candidate.employer_name.isnot(None),
        Candidate.employer_name != "",
        Candidate.account_status == "active",
        Candidate.email.isnot(None),
        Candidate.email != "",
        Candidate.joining_date.isnot(None),
    ).all()

    sent_days = {}
    if candidates:
        rows = DocumentReminderLog.query.filter(
            DocumentReminderLog.candidate_id.in_([c.id for c in candidates])
        ).all()
        for r in rows:
            sent_days.setdefault(r.candidate_id, set()).add(r.reminder_day)

    result = {"checked": len(candidates), "sent": 0, "failed": 0, "would_send": []}

    for c in candidates:
        days = (now - c.joining_date).days
        if days < step or days >= step + GRACE_DAYS:
            continue
        if step in sent_days.get(c.id, set()):
            continue
        missing = _missing_documents(c, settings)
        if not missing:
            continue

        if dry_run:
            result["would_send"].append(f"{c.full_name} <{c.email}> day {step}: {', '.join(missing)}")
            continue

        subject, body = _build_email(c, link, missing)
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
