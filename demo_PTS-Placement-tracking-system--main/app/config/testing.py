import os


class TestingConfig:
    ENV = "testing"
    DEBUG = False
    TESTING = True

    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret"

    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "placement_tracking_test")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")

    # Testing must NEVER touch a real database — hardcoded, no env override allowed.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    JSON_SORT_KEYS = False