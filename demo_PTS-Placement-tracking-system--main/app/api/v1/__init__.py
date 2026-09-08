from flask import Blueprint

api_v1_bp = Blueprint("api_v1", __name__)

from app.api.v1.auth import bp as auth_bp
from app.api.v1 import health  # noqa: F401

api_v1_bp.register_blueprint(auth_bp)
