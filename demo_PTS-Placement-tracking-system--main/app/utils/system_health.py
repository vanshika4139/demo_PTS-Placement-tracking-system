"""
Aggregates basic operational health signals for the super-admin System
Health page: MySQL connectivity, Redis connectivity, key table row counts,
and how long the app process has been running since its last restart.

Every check is wrapped so a single failing check (e.g. Redis down) never
breaks the whole page - each section reports its own availability.
"""

import os
import time
import logging

from sqlalchemy import text

from app.extensions import db
from app.models import (
    ActivityLog,
    Batch,
    Candidate,
    LoginHistory,
    Notification,
    Organization,
    Scheme,
    User,
)

logger = logging.getLogger(__name__)

# Recorded once, the first time this module is imported (i.e. at app
# startup) - gives a simple "time since last restart" without needing a
# dedicated table or extra process tracking.
_APP_STARTED_AT = time.time()


def get_app_uptime_seconds():
    return int(time.time() - _APP_STARTED_AT)


def format_duration(total_seconds):
    """Turns a second count into a short human string like '2d 4h 13m'."""
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def check_mysql():
    """Runs a trivial query to confirm the DB connection actually works,
    not just that a connection object exists."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"available": True, "error": None}
    except Exception as exc:
        logger.warning("system_health: MySQL check failed (%s)", exc)
        return {"available": False, "error": str(exc)}


def check_redis():
    """Same pattern as report_cache/rate_limit's own Redis clients - a
    short-timeout, independent connection so this check doesn't hang the
    page if Redis is unreachable."""
    try:
        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return {"available": True, "error": None}
    except Exception as exc:
        logger.warning("system_health: Redis check failed (%s)", exc)
        return {"available": False, "error": str(exc)}


def get_table_counts():
    """Row counts for the tables that matter most for a quick sanity check.
    Each count is independent - one failing table (e.g. missing after a
    partial migration) doesn't blank out the rest."""
    tables = {
        "Organizations": Organization,
        "Users": User,
        "Candidates": Candidate,
        "Batches": Batch,
        "Schemes": Scheme,
        "Activity Log Entries": ActivityLog,
        "Login History Entries": LoginHistory,
        "Notifications": Notification,
    }

    counts = {}
    for label, model in tables.items():
        try:
            counts[label] = model.query.count()
        except Exception as exc:
            logger.warning("system_health: count failed for %s (%s)", label, exc)
            counts[label] = None
    return counts


def get_system_health():
    return {
        "mysql": check_mysql(),
        "redis": check_redis(),
        "table_counts": get_table_counts(),
        "uptime_seconds": get_app_uptime_seconds(),
        "uptime_display": format_duration(get_app_uptime_seconds()),
    }