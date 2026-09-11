import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

from flask import Flask

from app.api.v1 import api_v1_bp
from app.config import get_config
from app.extensions import init_extensions
from app.routes import health_bp
from app.routes.frontend import frontend_bp
from app.services.scheduler import init_scheduler
from app.utils.error_handlers import register_error_handlers
from app.utils.logging import configure_logging
from app.utils.permissions import has_permission


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application instance."""
    config_name = config_name or os.getenv("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    )

    configure_logging(app)
    init_extensions(app)
    register_error_handlers(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(frontend_bp)
    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")

    # Daily billing cycle (invoice generation, renewal reminders, overdue
    # sweep, auto-suspend) - see app/services/scheduler.py. Registered here,
    # after extensions/blueprints are set up, so the scheduler thread never
    # starts against a half-configured app.
    init_scheduler(app)

    @app.context_processor
    def inject_permission_helper():
        """Makes has_permission(session.user, 'code') callable directly inside
        Jinja templates, so the sidebar and backend routes always agree on
        who can see/do what."""
        return {"has_permission": has_permission}

    return app