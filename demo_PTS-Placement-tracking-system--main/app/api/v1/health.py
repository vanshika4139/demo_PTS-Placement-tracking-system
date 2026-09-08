from flask import jsonify

from app.api.v1 import api_v1_bp


@api_v1_bp.get("/health")
def api_health():
    return jsonify(
        {
            "success": True,
            "message": "API is healthy",
            "data": {"service": "placement-tracking-system"},
            "errors": None,
            "meta": {},
        }
    )
