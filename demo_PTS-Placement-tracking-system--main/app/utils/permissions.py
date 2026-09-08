"""
Permission-checking utilities for the RBAC system.

Precedence (highest to lowest):
    1. Super Admin        -> always allowed
    2. User-specific override -> force-allow or force-deny, overrides role
    3. Role permission    -> the role's assigned permissions
    4. Default             -> DENY

PERFORMANCE: A user's effective permission set is cached in Redis for
PERMISSION_CACHE_SECONDS so we don't run the role/permission/override join
query on every single request. The cache is invalidated (deleted) immediately
whenever something that affects permissions changes: role assignment, role's
permission set, or a user's individual override. See invalidate_user_permission_cache().

Fails OPEN on Redis errors -> falls back to querying the database directly,
so a Redis outage degrades performance, not correctness.

Usage in routes:
    from app.utils.permissions import require_permission

    @frontend_bp.route("/organization/candidates/create", methods=["GET", "POST"])
    @login_required
    @require_permission("candidate.create")
    def organization_candidate_create():
        ...
"""

import json
import os
from functools import wraps

import redis
from flask import flash, redirect, session, url_for

from app.extensions import db
from app.models import Permission, RolePermission, UserPermissionOverride, UserRole

PERMISSION_CACHE_SECONDS = 300  # 5 minutes

_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    return _redis_client


def _cache_key(user_id):
    return f"permcache:{user_id}"


def _compute_user_permission_codes(user_id):
    """The actual database query - no caching here. Called on cache miss."""
    role_rows = (
        db.session.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.is_deleted == False,
            RolePermission.is_deleted == False,
            Permission.is_deleted == False,
        )
        .all()
    )
    codes = {code for (code,) in role_rows}

    override_rows = (
        db.session.query(Permission.code, UserPermissionOverride.is_allowed)
        .join(UserPermissionOverride, UserPermissionOverride.permission_id == Permission.id)
        .filter(
            UserPermissionOverride.user_id == user_id,
            UserPermissionOverride.is_deleted == False,
            Permission.is_deleted == False,
        )
        .all()
    )
    for code, is_allowed in override_rows:
        if is_allowed:
            codes.add(code)
        else:
            codes.discard(code)

    return codes


def get_user_permission_codes(user_id):
    """Return the set of permission codes this user effectively has.
    Checks Redis cache first; falls back to the database on a miss or if
    Redis is unreachable."""
    try:
        client = _get_redis_client()
        cached = client.get(_cache_key(user_id))
        if cached is not None:
            return set(json.loads(cached))
    except Exception:
        pass  # Redis unavailable - fall through to direct DB query

    codes = _compute_user_permission_codes(user_id)

    try:
        client = _get_redis_client()
        client.setex(_cache_key(user_id), PERMISSION_CACHE_SECONDS, json.dumps(list(codes)))
    except Exception:
        pass  # Caching failed - not fatal, just means next request recomputes too

    return codes


def invalidate_user_permission_cache(user_id):
    """Call this immediately after anything changes this user's effective
    permissions: their role assignment, their overrides, or (for everyone
    with a given role) that role's permission set."""
    try:
        client = _get_redis_client()
        client.delete(_cache_key(user_id))
    except Exception:
        pass


def invalidate_role_permission_cache(role_id):
    """Call this after a role's permissions change (RolePermission rows added/
    removed). Clears the cache for every user currently assigned that role,
    since the change affects all of them at once."""
    try:
        user_ids = [
            ur.user_id
            for ur in UserRole.query.filter_by(role_id=role_id, is_deleted=False).all()
        ]
        client = _get_redis_client()
        if user_ids:
            client.delete(*[_cache_key(uid) for uid in user_ids])
    except Exception:
        pass


def has_permission(session_user, permission_code):
    """session_user is the dict stored in session['user']."""
    if not session_user:
        return False
    if session_user.get("is_super_admin"):
        return True
    user_id = session_user.get("id")
    if not user_id:
        return False
    codes = get_user_permission_codes(user_id)
    return permission_code in codes


def require_permission(permission_code):
    """Route decorator. Must be used AFTER @login_required (closer to the function)
    so session['user'] is guaranteed to exist by the time this runs.

    IMPORTANT: the fallback redirect always goes to /no-access, a route that
    itself carries NO permission requirement. Redirecting to
    organization_dashboard/super_admin_dashboard here is what used to cause
    an infinite redirect loop for a permission-less user, since those routes
    are themselves gated by a permission check (e.g. dashboard.view) that
    would fail again and redirect right back here."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            session_user = session.get("user")
            if not has_permission(session_user, permission_code):
                flash("You do not have permission to perform this action.", "error")
                return redirect(url_for("frontend.no_access"))
            return view_func(*args, **kwargs)
        return wrapped
    return decorator