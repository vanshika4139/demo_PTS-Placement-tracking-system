from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User
from app.models.login_history import LoginHistory
from app.routes.frontend import PasswordResetOTP

EMAIL = "admin@example.com"
PASSWORD = "StrongPass#1"


def _no_redis():
    raise RuntimeError("no redis in tests")


@pytest.fixture()
def app(monkeypatch):
    app = create_app("testing")
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///:memory:")
    app.config["STAFF_2FA_ENABLED"] = True
    monkeypatch.setattr("app.utils.rate_limit._get_redis_client", _no_redis)  # limiter fails open
    sent = []
    monkeypatch.setattr("app.utils.email.send_otp_email", lambda email, code: sent.append((email, code)))
    app.sent_otps = sent
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(User(
            email=EMAIL, password_hash=generate_password_hash(PASSWORD), full_name="Admin",
            organization_id=None, is_super_admin=True, is_active=True,
        ))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def post_login(client, password=PASSWORD):
    return client.post("/login", data={"email": EMAIL, "password": password})


def session_user(client):
    with client.session_transaction() as s:
        return s.get("user")


def test_password_step_sends_otp_and_creates_no_session(client, app):
    resp = post_login(client)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login/verify-otp")
    assert session_user(client) is None
    assert app.sent_otps and app.sent_otps[0][0] == EMAIL
    assert LoginHistory.query.filter_by(success=True).count() == 0


def test_correct_otp_completes_the_login(client, app):
    post_login(client)
    code = app.sent_otps[0][1]
    resp = client.post("/login/verify-otp", data={"otp": code})
    assert resp.status_code == 302
    assert session_user(client)["email"] == EMAIL
    assert LoginHistory.query.filter_by(success=True).count() == 1


def test_wrong_otp_does_not_log_in(client, app):
    post_login(client)
    resp = client.post("/login/verify-otp", data={"otp": "000000"})
    assert resp.status_code == 200
    assert session_user(client) is None


def test_wrong_password_sends_no_otp(client, app):
    resp = post_login(client, password="wrong")
    assert resp.status_code == 200
    assert app.sent_otps == []
    assert session_user(client) is None


def test_verify_page_without_a_password_step_redirects_to_login(client):
    resp = client.post("/login/verify-otp", data={"otp": "123456"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert session_user(client) is None


def test_otp_cannot_be_used_twice(client, app):
    post_login(client)
    code = app.sent_otps[0][1]
    assert client.post("/login/verify-otp", data={"otp": code}).status_code == 302
    client.get("/logout")
    # a fresh password step must not accept the already used OTP
    with client.session_transaction() as s:
        s["staff_otp_pending_id"] = User.query.filter_by(email=EMAIL).first().id
        s["staff_otp_email"] = EMAIL
    resp = client.post("/login/verify-otp", data={"otp": code})
    assert resp.status_code == 200 and session_user(client) is None


def test_deactivated_user_cannot_finish_after_the_password_step(client, app):
    post_login(client)
    code = app.sent_otps[0][1]
    user = User.query.filter_by(email=EMAIL).first()
    user.is_active = False
    db.session.commit()
    client.post("/login/verify-otp", data={"otp": code})
    assert session_user(client) is None


def test_2fa_can_be_switched_off(client, app):
    app.config["STAFF_2FA_ENABLED"] = False
    resp = post_login(client)
    assert resp.status_code == 302 and not resp.headers["Location"].endswith("/login/verify-otp")
    assert session_user(client)["email"] == EMAIL
    assert app.sent_otps == []