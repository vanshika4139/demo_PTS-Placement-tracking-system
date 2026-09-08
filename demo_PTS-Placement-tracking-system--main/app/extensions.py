from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from redis import Redis


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()


def init_extensions(app) -> None:
    """Initialize third-party extensions for the Flask application."""
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": "*"}},
        supports_credentials=True,
    )

    app.extensions["redis_client"] = Redis.from_url(app.config["REDIS_URL"])
