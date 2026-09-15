from __future__ import annotations

from datetime import timedelta

from app.extensions import db
from app.models import Candidate, FollowUpCheckpoint

# Same 6 checkpoints frontend.py used to define locally as CHECKPOINT_LABELS -
# moved here so there's one definition instead of two that could drift apart.
FOLLOW_UP_CHECKPOINTS = [
    ("Month 1", timedelta(days=30)),
    ("Month 2", timedelta(days=60)),
    ("Month 3", timedelta(days=90)),
    ("Month 6", timedelta(days=180)),
    ("Month 9", timedelta(days=270)),
    ("Month 12", timedelta(days=365)),
]


class CandidateLifecycleService:
    """Owns two things for a Candidate: validating training_status moves,
    and generating post-placement follow-up checkpoints.

    WIRING NOTE: the original version of this class modeled "placed" and
    "month_1_verification".."month_12_verification" as training_status
    values, and built follow-up rows with a raw text() SQL INSERT. Neither
    matched how the rest of the app actually works:
      - training_status only ever holds training_started / training_completed
        / dropped_out anywhere else in this codebase (the edit form's
        dropdown, dashboard stage counts, candidate list filters). Placement
        is tracked by Candidate.employer_name being set, not by a
        training_status value.
      - Month-based follow-ups are the existing FollowUpCheckpoint model,
        already populated via the ORM by frontend.py's (now removed)
        _ensure_checkpoints() once a candidate has both employer_name and
        joining_date.

    This version keeps the class's job but matches that reality:
    VALID_TRANSITIONS only covers real training_status values, and follow-up
    generation goes through FollowUpCheckpoint directly instead of raw SQL.
    frontend.py now calls this class instead of keeping its own separate
    copy of either piece of logic.
    """

    VALID_TRANSITIONS = {
        "training_started": {"training_completed", "dropped_out"},
        "training_completed": {"dropped_out"},
        "dropped_out": set(),
    }

    def validate_transition(self, current_status: str, new_status: str) -> None:
        """Raises ValueError if new_status isn't a currently-allowed move
        from current_status. Doesn't touch the database - split out from
        transition() so a caller that's already mid-way through saving
        several other fields on the same Candidate (and will commit once at
        the end) can validate without triggering an early partial commit.
        """
        allowed = self.VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot move a candidate from '{current_status}' to '{new_status}'."
            )

    def transition(self, candidate: Candidate, new_status: str) -> Candidate:
        """Standalone transition + commit, for callers that are ONLY
        changing training_status (not already inside a larger multi-field
        save with its own commit) - e.g. a future bulk status-change action.
        Resets verification_status back to "pending", since a status change
        means whatever was previously verified no longer applies.
        """
        self.validate_transition(candidate.training_status, new_status)
        candidate.training_status = new_status
        candidate.verification_status = "pending"
        db.session.add(candidate)
        db.session.commit()
        return candidate

    def ensure_follow_ups(self, candidate: Candidate) -> None:
        """Create the 6 standard post-placement follow-up checkpoints for
        candidate if none exist yet. No-op if the candidate has no
        joining_date (nothing to anchor due dates to) or already has
        checkpoints. Safe to call every time a placed candidate is
        viewed/saved - this is what frontend.py's old _ensure_checkpoints()
        did, moved here so there's one implementation instead of two.
        """
        if not candidate.joining_date:
            return
        existing = FollowUpCheckpoint.query.filter_by(candidate_id=candidate.id).count()
        if existing > 0:
            return
        for label, offset in FOLLOW_UP_CHECKPOINTS:
            db.session.add(FollowUpCheckpoint(
                candidate_id=candidate.id,
                label=label,
                due_date=candidate.joining_date + offset,
                status="pending",
            ))
        db.session.commit()