import logging
import os
from logging.config import dictConfig


def configure_logging(app) -> None:
    """Configure structured logging for the Flask app."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "standard",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": os.getenv("LOG_LEVEL", "INFO"),
            },
        }
    )
    app.logger.info("Logging configured")
