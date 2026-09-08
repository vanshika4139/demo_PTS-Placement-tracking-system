from __future__ import annotations

from datetime import datetime, timedelta

from app.extensions import db
from app.models import Candidate


class CandidateLifecycleService:
    """Manage candidate lifecycle transitions and follow-up checkpoints."""

    VALID_TRANSITIONS = {
        "training_started": {"training_completed"},
        "training_completed": {"placed"},
        "placed": {"month_1_verification"},
        "month_1_verification": {"month_2_verification"},
        "month_2_verification": {"month_3_verification"},
        "month_3_verification": {"month_6_verification"},
        "month_6_verification": {"month_9_verification"},
        "month_9_verification": {"month_12_verification"},
    }

    def transition(self, candidate: Candidate, new_status: str) -> Candidate:
        if new_status not in self.VALID_TRANSITIONS.get(candidate.training_status, set()):
            raise ValueError(f"Invalid transition from {candidate.training_status} to {new_status}")

        candidate.training_status = new_status
        candidate.verification_status = "pending"
        db.session.add(candidate)
        db.session.commit()

        if new_status == "placed":
            self.generate_follow_ups(candidate)

        return candidate

    def generate_follow_ups(self, candidate: Candidate) -> None:
        if not candidate.joining_date:
            return

        checkpoints = [
            ("month_1", timedelta(days=30)),
            ("month_2", timedelta(days=60)),
            ("month_3", timedelta(days=90)),
            ("month_6", timedelta(days=180)),
            ("month_9", timedelta(days=270)),
            ("month_12", timedelta(days=365)),
        ]

        for label, offset in checkpoints:
            due_date = candidate.joining_date + offset
            db.session.execute(
                text(
                    "INSERT INTO follow_up_checkpoints (candidate_id, label, due_date, status) VALUES (:candidate_id, :label, :due_date, :status)"
                ),
                {"candidate_id": candidate.id, "label": label, "due_date": due_date, "status": "pending"},
            )

        db.session.commit()

