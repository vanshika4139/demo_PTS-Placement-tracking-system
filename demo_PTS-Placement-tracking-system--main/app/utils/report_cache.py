"""
Fail-open Redis caching for expensive dashboard/report aggregation queries.

Same pattern as app.utils.permissions and app.utils.rate_limit: if Redis is
down or unreachable, we never raise - we just skip the cache and run the
wrapped function directly against the DB.

Usage:

    from app.utils.report_cache import cached_report, invalidate_report_cache

    @cached_report(key_prefix="dashboard:org")
    def get_organization_dashboard_data(organization_id):
        # ... heavy aggregation queries ...
        return {...}   # MUST be plain JSON-serializable data (dict/list/str/number)

    @frontend_bp.route("/organization/dashboard")
    def organization_dashboard():
        data = get_organization_dashboard_data(org_id)
        return render_template("organization/dashboard.html", **data)

    # Wherever the underlying data changes, right after db.session.commit():
    invalidate_report_cache("dashboard:org")
"""

import json
import logging
import os
from datetime import date, datetime
from functools import wraps

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300  # 5 minutes

# Keys used to track cache hit/miss counts for the super-admin monitoring page.
# Kept outside the "report_cache:<prefix>:..." namespace so a "Clear Cache"
# never wipes the stats themselves.
STATS_HITS_KEY = "report_cache_stats:hits"
STATS_MISSES_KEY = "report_cache_stats:misses"

_redis_client = None
_redis_available = True  # flips to False after the first connection failure


def _get_redis_client():
    """Lazily create (and cache) a Redis client. Returns None if Redis is
    unreachable - callers must treat None as "caching disabled right now"."""
    global _redis_client, _redis_available

    if not _redis_available:
        return None

    if _redis_client is None:
        try:
            import redis  # local import so this module never hard-fails to import

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            _redis_client = client
        except Exception as exc:
            logger.warning("report_cache: Redis unavailable, falling back to direct queries (%s)", exc)
            _redis_available = False
            _redis_client = None

    return _redis_client


def _json_default(obj):
    """Best-effort fallback for datetime/date objects that slip through.
    Cached functions should already convert these themselves (e.g. via
    .strftime()) - this is just a safety net so a stray datetime doesn't
    crash the whole request instead of silently skipping the cache."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _build_cache_key(key_prefix, args, kwargs):
    parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    suffix = ":".join(parts) if parts else "default"
    return f"report_cache:{key_prefix}:{suffix}"


def cached_report(key_prefix, ttl_seconds=DEFAULT_TTL_SECONDS):
    """Decorator: cache a function's return value in Redis for ttl_seconds.

    The cache key is built from key_prefix + the function's call arguments,
    so e.g. get_organization_dashboard_data(org_id) caches separately per
    organization automatically.

    IMPORTANT: the wrapped function must return plain JSON-serializable data
    only (dict/list/str/number). Do not return SQLAlchemy model objects or
    raw datetime objects - call .strftime() etc. *inside* the cached function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            client = _get_redis_client()
            cache_key = _build_cache_key(key_prefix, args, kwargs)

            if client is not None:
                try:
                    cached_value = client.get(cache_key)
                    if cached_value is not None:
                        _record_cache_event(client, hit=True)
                        return json.loads(cached_value)
                except Exception as exc:
                    logger.warning("report_cache: read failed for %s (%s)", cache_key, exc)
                else:
                    # Read succeeded but the key wasn't there - a genuine miss.
                    _record_cache_event(client, hit=False)

            result = func(*args, **kwargs)

            if client is not None:
                try:
                    client.setex(cache_key, ttl_seconds, json.dumps(result, default=_json_default))
                except Exception as exc:
                    logger.warning("report_cache: write failed for %s (%s)", cache_key, exc)

            return result

        return wrapper

    return decorator


def _record_cache_event(client, hit):
    """Increment the hit/miss counters. Best-effort only - never allowed to
    affect the actual cache read/write path."""
    try:
        client.incr(STATS_HITS_KEY if hit else STATS_MISSES_KEY)
    except Exception:
        pass


def get_cache_overview():
    """Everything the super-admin 'Cache Monitor' page needs in one call:
    Redis connectivity, every active report_cache key with its remaining
    TTL, hit/miss counters, and a rough breakdown of how many keys exist
    under each other Redis namespace used in the app (permcache, ratelimit).

    Fail-open: if Redis is unreachable, returns redis_available=False with
    empty/zeroed data rather than raising.
    """
    client = _get_redis_client()

    if client is None:
        return {
            "redis_available": False,
            "cache_keys": [],
            "total_keys": 0,
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "other_namespaces": [],
        }

    keys_info = []
    namespace_counts = {}

    try:
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor=cursor, count=200)
            for raw_key in batch:
                key_str = raw_key.decode() if isinstance(raw_key, bytes) else raw_key

                if key_str in (STATS_HITS_KEY, STATS_MISSES_KEY):
                    continue

                namespace = key_str.split(":", 1)[0]
                namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1

                if key_str.startswith("report_cache:"):
                    try:
                        ttl = client.ttl(raw_key)
                    except Exception:
                        ttl = -1
                    keys_info.append({"key": key_str, "ttl_seconds": ttl})
            if cursor == 0:
                break
    except Exception as exc:
        logger.warning("report_cache: overview scan failed (%s)", exc)

    keys_info.sort(key=lambda item: item["key"])

    hits = 0
    misses = 0
    try:
        hits = int(client.get(STATS_HITS_KEY) or 0)
        misses = int(client.get(STATS_MISSES_KEY) or 0)
    except Exception:
        pass

    total_events = hits + misses
    hit_rate = round((hits / total_events) * 100, 1) if total_events else 0.0

    other_namespaces = [
        {"namespace": ns, "key_count": count}
        for ns, count in sorted(namespace_counts.items())
        if ns != "report_cache"
    ]

    return {
        "redis_available": True,
        "cache_keys": keys_info,
        "total_keys": len(keys_info),
        "hits": hits,
        "misses": misses,
        "hit_rate": hit_rate,
        "other_namespaces": other_namespaces,
    }


def clear_all_report_cache():
    """Delete every cached report/dashboard entry across all prefixes
    (used by the super-admin 'Clear Cache' button). Hit/miss counters are
    left untouched so the ratio stays meaningful across a manual clear.

    Returns the number of keys removed, or False if Redis is unreachable.
    """
    client = _get_redis_client()
    if client is None:
        return False

    try:
        cursor = 0
        removed = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match="report_cache:*", count=200)
            if keys:
                client.delete(*keys)
                removed += len(keys)
            if cursor == 0:
                break
        return removed
    except Exception as exc:
        logger.warning("report_cache: clear_all failed (%s)", exc)
        return False


def get_cache_key_data(key):
    """Return the cached value stored under a single report_cache key,
    parsed as JSON when possible. Used by the 'View' link on the cache
    monitor page so an admin can see exactly what's cached before deciding
    to delete it.

    Read-only, and only ever touches report_cache: keys - never permcache:
    or ratelimit: keys. Returns None if the key is missing, Redis is
    unreachable, or the key isn't in our namespace.
    """
    if not key or not key.startswith("report_cache:"):
        return None

    client = _get_redis_client()
    if client is None:
        return None

    try:
        raw = client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return raw.decode(errors="replace") if isinstance(raw, bytes) else raw
    except Exception as exc:
        logger.warning("report_cache: get_cache_key_data failed for %s (%s)", key, exc)
        return None


def delete_cache_key(key):
    """Delete a single report_cache key (the per-row Delete button on the
    cache monitor page, for when an admin wants to clear just one stale
    entry instead of everything).

    Returns True if a key was actually removed, False otherwise (missing,
    not a report_cache: key, or Redis unreachable).
    """
    if not key or not key.startswith("report_cache:"):
        return False

    client = _get_redis_client()
    if client is None:
        return False

    try:
        return client.delete(key) > 0
    except Exception as exc:
        logger.warning("report_cache: delete_cache_key failed for %s (%s)", key, exc)
        return False


def invalidate_report_cache(key_prefix):
    """Delete every cached entry under key_prefix (e.g. "reports",
    "dashboard:org", "dashboard:super_admin"). Fail-open: if Redis is down,
    this is a silent no-op - it never raises.

    Call this immediately after db.session.commit() wherever candidate,
    placement/verification, or batch/scheme data changes.
    """
    client = _get_redis_client()
    if client is None:
        return

    try:
        pattern = f"report_cache:{key_prefix}:*"
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                client.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:
        logger.warning("report_cache: invalidation failed for prefix %s (%s)", key_prefix, exc)