from flask import Blueprint

health_bp = Blueprint("health", __name__)

from app.routes.health import *
