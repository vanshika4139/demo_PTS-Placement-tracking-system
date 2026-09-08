from flask import jsonify

from app.routes import health_bp


@health_bp.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "placement-tracking-system",
            "environment": "development",
        }
    )
