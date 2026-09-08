from functools import wraps

from flask import g, jsonify, request
from flask_jwt_extended import get_jwt


def tenant_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        organization_id = claims.get("organization_id")
        if not organization_id:
            return jsonify({"success": False, "message": "Organization context required", "data": None, "errors": {"detail": "missing organization"}, "meta": {}}), 400

        g.organization_id = organization_id
        return fn(*args, **kwargs)

    return wrapper
