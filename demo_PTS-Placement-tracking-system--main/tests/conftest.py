"""
Shared pytest fixtures.

GOLDEN RULE: these tests NEVER call db.drop_all() or db.create_all().
That mistake wiped the real database once already. Tests only insert
specific, clearly-named rows and delete exactly those rows afterwards -
nothing else is ever touched.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app import create_app


@pytest.fixture()
def app():
    """Uses the same database your app normally runs against.
    Does NOT create or drop any tables - the schema is left exactly as-is."""
    application = create_app("development")
    application.config.update(TESTING=True)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def login_as(client, user_dict):
    """Simulates a logged-in session without hitting /login."""
    with client.session_transaction() as sess:
        sess["user"] = user_dict
        sess.permanent = True