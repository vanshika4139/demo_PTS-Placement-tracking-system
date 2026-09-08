"""
Simple Redis-backed rate limiter for sensitive auth routes (login, OTP requests).

Fails OPEN: if Redis is unreachable for any reason, requests are allowed through
rather than locking everyone out - availability of login is more important than
this specific protection layer.
"""

import logging
import os
from functools import wraps

import redis
from flask import flash, redirect, request, url_for

logger = logging.getLogger(__name__)

_redis_client = None

# Known rate-limited routes and their configured limits, kept here purely for
# DISPLAY on the super-admin monitor page. The limiter itself only stores the
# running attempt count in Redis, not the threshold - so if you add a new
# @rate_limit(...) call elsewhere, add its prefix/limits here too so the
# monitor page can show "3 / 5 attempts" instead of just "3 attempts".
KNOWN_RATE_LIMITS = {
    "login": {"max_attempts": 5, "window_seconds": 900, "label": "Login"},
    "forgot_password": {"max_attempts": 3, "window_seconds": 600, "label": "Forgot Password"},
    "verify_otp": {"max_attempts": 5, "window_seconds": 600, "label": "Verify OTP"},
}


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    return _redis_client


def rate_limit(key_prefix, max_attempts=5, window_seconds=900):
    """Limits POST requests to this route to `max_attempts` per `window_seconds`,
    keyed by client IP. GET requests are never limited (only form submissions count).

    window_seconds default 900 = 15 minutes.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if request.method != "POST":
                return view_func(*args, **kwargs)

            client_ip = request.remote_addr or "unknown"
            redis_key = f"ratelimit:{key_prefix}:{client_ip}"

            try:
                client = _get_redis_client()
                count = client.incr(redis_key)
                if count == 1:
                    client.expire(redis_key, window_seconds)

                if count > max_attempts:
                    ttl = client.ttl(redis_key)
                    minutes = max(1, (ttl or window_seconds) // 60)
                    flash(f"Too many attempts. Please try again in {minutes} minute(s).", "error")
                    return redirect(url_for(request.endpoint, **kwargs))
            except Exception:
                # Redis unavailable - fail open, don't block the user
                pass

            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def get_rate_limit_overview():
    """Everything the super-admin 'Rate Limit Monitor' page needs: every
    active ratelimit:* key currently in Redis, parsed into its route prefix
    and client IP, with the current attempt count and remaining TTL.

    Fail-open: if Redis is unreachable, returns redis_available=False with
    an empty list rather than raising.
    """
    try:
        client = _get_redis_client()
        client.ping()
    except Exception as exc:
        logger.warning("rate_limit: Redis unavailable for overview (%s)", exc)
        return {"redis_available": False, "entries": [], "total_keys": 0, "blocked_count": 0}

    entries = []
    try:
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor=cursor, match="ratelimit:*", count=200)
            for raw_key in batch:
                key_str = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                # key format: ratelimit:<prefix>:<ip>
                parts = key_str.split(":", 2)
                if len(parts) < 3:
                    continue
                _, prefix, ip = parts

                try:
                    count = int(client.get(raw_key) or 0)
                except Exception:
                    count = 0
                try:
                    ttl = client.ttl(raw_key)
                except Exception:
                    ttl = -1

                limit_info = KNOWN_RATE_LIMITS.get(prefix, {})
                max_attempts = limit_info.get("max_attempts")

                entries.append({
                    "key": key_str,
                    "prefix": prefix,
                    "label": limit_info.get("label", prefix.replace("_", " ").title()),
                    "ip": ip,
                    "count": count,
                    "max_attempts": max_attempts,
                    "is_blocked": bool(max_attempts is not None and count > max_attempts),
                    "ttl_seconds": ttl,
                })
            if cursor == 0:
                break
    except Exception as exc:
        logger.warning("rate_limit: overview scan failed (%s)", exc)

    entries.sort(key=lambda e: (-e["count"], e["prefix"]))

    return {
        "redis_available": True,
        "entries": entries,
        "total_keys": len(entries),
        "blocked_count": sum(1 for e in entries if e["is_blocked"]),
    }


def clear_rate_limit_key(key):
    """Manually clear a single rate-limit key - e.g. to unblock a legitimate
    user who got caught by the limiter. Only ever touches ratelimit: keys.
    Returns True if a key was actually removed."""
    if not key or not key.startswith("ratelimit:"):
        return False
    try:
        client = _get_redis_client()
        return client.delete(key) > 0
    except Exception as exc:
        logger.warning("rate_limit: clear_rate_limit_key failed for %s (%s)", key, exc)
        return False