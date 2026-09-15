from functools import wraps

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

from app.models import User
from app.utils.permissions import has_permission


def permission_required(permission_code: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            user_id = claims.get("sub")
            if not user_id:
                return jsonify({"success": False, "message": "Unauthorized", "data": None, "errors": {"detail": "missing identity"}, "meta": {}}), 401

            user = User.query.get(user_id)
            if not user or not user.is_active:
                return jsonify({"success": False, "message": "Unauthorized", "data": None, "errors": {"detail": "invalid user"}, "meta": {}}), 401

            # BUG FIX: this used to hardcode
            #     if permission_code == "candidate.create": return fn(*args, **kwargs)
            # which let ANY authenticated, active, non-super-admin user call
            # candidate.create-protected API routes regardless of their actual
            # role or permission overrides - a total backdoor around RBAC for
            # that one permission code, only reachable via /api/v1 (web routes
            # were never affected - they go through app.utils.permissions.
            # require_permission, which does this correctly).
            #
            # Now it runs the SAME check web routes use: role permissions +
            # user-specific overrides + super-admin bypass, Redis-cached via
            # get_user_permission_codes(). has_permission() expects a
            # session-shaped dict, so we build the minimal equivalent from the
            # JWT-resolved `user` here instead of Flask's session.
            session_like_user = {"id": user.id, "is_super_admin": user.is_super_admin}
            if has_permission(session_like_user, permission_code):
                return fn(*args, **kwargs)

            return jsonify({"success": False, "message": "Forbidden", "data": None, "errors": {"detail": "permission denied"}, "meta": {}}), 403

        return wrapper

    return decorator