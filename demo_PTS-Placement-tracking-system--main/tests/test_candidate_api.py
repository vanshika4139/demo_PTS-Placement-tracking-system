import io
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Organization
from app.models.candidate import Candidate
from app.models.candidate_consent import CandidateConsent
from app.models.salary_slip import SalarySlip
from app.routes.frontend import CONSENT_NOTICE_VERSION, PasswordResetOTP

PASSWORD = "Secret#123"
MOBILE = "9876543210"


@pytest.fixture()
def app(monkeypatch):
    app = create_app("testing")
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///:memory:")
    # no Redis in tests, and no real emails
    monkeypatch.setattr("app.api.v1.candidate._too_many", lambda *a, **k: False)
    sent = []
    monkeypatch.setattr("app.utils.email.send_otp_email", lambda email, code: sent.append((email, code)))
    app.sent_otps = sent
    with app.app_context():
        db.drop_all()
        db.create_all()
        org = Organization(organization_code="ACME-ORG", organization_name="Acme Org", status=1)
        org.id = 1
        db.session.add(org)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_candidate(reg="REG001", email=None, password=PASSWORD, mobile=MOBILE, status="active", consent=True):
    c = Candidate(
        organization_id=1, registration_number=reg, full_name="Test " + reg, mobile=mobile,
        email=email, password_hash=generate_password_hash(password), account_status=status,
    )
    db.session.add(c)
    db.session.commit()
    if consent:
        db.session.add(CandidateConsent(
            candidate_id=c.id, organization_id=1, notice_version=CONSENT_NOTICE_VERSION,
            consented_at=datetime.utcnow(),
        ))
        db.session.commit()
    return c


def login(client, reg="REG001", password=PASSWORD):
    return client.post("/api/v1/candidate/login", json={"registration_number": reg, "password": password})


def bearer(token):
    return {"Authorization": "Bearer " + token}


def tokens(client, reg="REG001", password=PASSWORD):
    data = login(client, reg, password).get_json()["data"]
    return data["access_token"], data["refresh_token"]


# ---------- login ----------

def test_wrong_password_is_401(client):
    make_candidate()
    assert login(client, password="wrong").status_code == 401


def test_unknown_registration_number_is_401(client):
    assert login(client, reg="NOPE").status_code == 401


def test_blocked_candidate_is_403(client):
    make_candidate(status="blocked")
    assert login(client).status_code == 403


def test_login_without_email_returns_tokens_directly(client):
    make_candidate()
    body = login(client).get_json()["data"]
    assert body["access_token"] and body["refresh_token"]
    assert body["consent_required"] is False
    assert body["password_change_required"] is False


# ---------- OTP ----------

def test_login_with_email_gives_no_access_token_until_otp(client, app):
    make_candidate(email="c@example.com")
    resp = login(client)
    data = resp.get_json()["data"]
    assert resp.status_code == 200
    assert data["otp_required"] is True
    assert "access_token" not in data
    assert app.sent_otps and app.sent_otps[0][0] == "c@example.com"
    # the OTP token must not work as a normal access token
    assert client.get("/api/v1/candidate/me", headers=bearer(data["otp_token"])).status_code == 403


def test_verify_otp_gives_tokens_and_otp_token_is_single_use(client, app):
    make_candidate(email="c@example.com")
    otp_token = login(client).get_json()["data"]["otp_token"]
    code = PasswordResetOTP.query.filter_by(email="c@example.com").first().otp_code

    ok = client.post("/api/v1/candidate/verify-otp", json={"otp": code}, headers=bearer(otp_token))
    assert ok.status_code == 200
    assert ok.get_json()["data"]["access_token"]

    again = client.post("/api/v1/candidate/verify-otp", json={"otp": code}, headers=bearer(otp_token))
    assert again.status_code == 401


def test_wrong_otp_is_401(client):
    make_candidate(email="c@example.com")
    otp_token = login(client).get_json()["data"]["otp_token"]
    resp = client.post("/api/v1/candidate/verify-otp", json={"otp": "000000"}, headers=bearer(otp_token))
    assert resp.status_code == 401


# ---------- consent and default password gates ----------

def test_me_is_blocked_until_consent_and_password_change(client):
    make_candidate(password=MOBILE, consent=False)  # default password = mobile number
    access, _ = tokens(client, password=MOBILE)

    r = client.get("/api/v1/candidate/me", headers=bearer(access))
    assert r.status_code == 403 and r.get_json()["errors"]["detail"] == "consent_required"

    assert client.post("/api/v1/candidate/consent", json={"agree": False}, headers=bearer(access)).status_code == 400
    assert client.post("/api/v1/candidate/consent", json={"agree": True}, headers=bearer(access)).status_code == 200

    r = client.get("/api/v1/candidate/me", headers=bearer(access))
    assert r.status_code == 403 and r.get_json()["errors"]["detail"] == "password_change_required"

    bad = client.post("/api/v1/candidate/change-password", headers=bearer(access), json={
        "current_password": MOBILE, "new_password": MOBILE, "confirm_password": MOBILE})
    assert bad.status_code == 400
    good = client.post("/api/v1/candidate/change-password", headers=bearer(access), json={
        "current_password": MOBILE, "new_password": "NewPass#1", "confirm_password": "NewPass#1"})
    assert good.status_code == 200

    assert client.get("/api/v1/candidate/me", headers=bearer(access)).status_code == 200


def test_blocking_a_candidate_stops_an_existing_token(client):
    c = make_candidate()
    access, _ = tokens(client)
    assert client.get("/api/v1/candidate/me", headers=bearer(access)).status_code == 200
    c.account_status = "blocked"
    db.session.commit()
    assert client.get("/api/v1/candidate/me", headers=bearer(access)).status_code == 403


# ---------- token separation ----------

def test_staff_style_token_is_rejected_on_candidate_routes(client):
    c = make_candidate()
    t = create_access_token(identity=c.id, additional_claims={"is_super_admin": True})
    assert client.get("/api/v1/candidate/me", headers=bearer(t)).status_code == 403


def test_candidate_token_does_not_work_on_staff_routes(client):
    make_candidate()
    access, _ = tokens(client)
    resp = client.get("/api/v1/organizations/me/stats", headers=bearer(access))
    assert resp.status_code != 200 and resp.status_code < 500


def test_refresh_token_rotates_and_works_once(client):
    make_candidate()
    _, refresh = tokens(client)
    first = client.post("/api/v1/candidate/refresh", headers=bearer(refresh))
    assert first.status_code == 200
    assert first.get_json()["data"]["refresh_token"] != refresh
    assert client.post("/api/v1/candidate/refresh", headers=bearer(refresh)).status_code == 401


def test_access_token_cannot_be_used_to_refresh(client):
    make_candidate()
    access, _ = tokens(client)
    assert client.post("/api/v1/candidate/refresh", headers=bearer(access)).status_code in (401, 422)


# ---------- salary slips ----------

@pytest.fixture()
def slips_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # uploads go to a temp folder, not the real app/private_uploads
    monkeypatch.setattr("app.routes.frontend._storage_block_message", lambda *a, **k: None)


def upload(client, access, month, name="slip.pdf", content=b"%PDF-1.4 test"):
    return client.post(
        "/api/v1/candidate/salary-slips", headers=bearer(access), content_type="multipart/form-data",
        data={"month": month, "file": (io.BytesIO(content), name)},
    )


def test_slip_upload_list_and_download(client, slips_env):
    make_candidate()
    access, _ = tokens(client)
    month = datetime.utcnow().strftime("%Y-%m")

    assert upload(client, access, month).status_code == 201
    listed = client.get("/api/v1/candidate/salary-slips", headers=bearer(access)).get_json()["data"]["slips"]
    assert [s["month"] for s in listed] == [month]

    dl = client.get("/api/v1/candidate/salary-slips/%s/download" % listed[0]["id"], headers=bearer(access))
    assert dl.status_code == 200 and dl.data.startswith(b"%PDF")


def test_slip_rules_are_enforced(client, slips_env):
    make_candidate()
    access, _ = tokens(client)
    assert upload(client, access, "2999-01").status_code == 400                      # future month
    assert upload(client, access, "not-a-month").status_code == 400                  # bad month
    assert upload(client, access, "2024-01", name="slip.exe").status_code == 400     # bad type
    assert upload(client, access, "2024-01", content=b"").status_code == 400         # empty file
    assert upload(client, access, "2024-01", content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 400  # too big
    assert SalarySlip.query.count() == 0


def test_candidate_cannot_see_or_download_another_candidates_slip(client, slips_env):
    make_candidate(reg="REG001")
    make_candidate(reg="REG002")
    a, _ = tokens(client, reg="REG001")
    b, _ = tokens(client, reg="REG002")
    month = datetime.utcnow().strftime("%Y-%m")
    assert upload(client, a, month).status_code == 201
    slip_id = SalarySlip.query.first().id

    assert client.get("/api/v1/candidate/salary-slips", headers=bearer(b)).get_json()["data"]["slips"] == []
    stolen = client.get("/api/v1/candidate/salary-slips/%s/download" % slip_id, headers=bearer(b))
    assert stolen.status_code in (403, 404)