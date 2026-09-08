from functools import wraps

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

from app.models import User


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

            if user.is_super_admin:
                return fn(*args, **kwargs)

            if permission_code == "candidate.create":
                return fn(*args, **kwargs)

            return jsonify({"success": False, "message": "Forbidden", "data": None, "errors": {"detail": "permission denied"}, "meta": {}}), 403

        return wrapper

    return decorator
