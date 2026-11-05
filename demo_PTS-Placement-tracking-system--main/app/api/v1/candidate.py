"""Candidate (mobile app) API.

Mirrors the web candidate flow: password login, email OTP (when the candidate has an email),
privacy consent, forced change of the default password. Candidate tokens carry
user_type="candidate" so a staff token never works here and a candidate token never works on
staff routes. Every route works on g.candidate (taken from the token), never on an id sent by the app.
"""
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import (
    create_access_token, create_refresh_token, get_jwt, get_jwt_identity, verify_jwt_in_request,
)
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.candidate import Candidate

bp = Blueprint("candidate_api", __name__)

OTP_TOKEN_MINUTES = 10


def _resp(success, message, data=None, errors=None, status=200):
    return jsonify({"success": success, "message": message, "data": data, "errors": errors, "meta": {}}), status


def _fail(status, message, detail):
    return _resp(False, message, None, {"detail": detail}, status)


def _too_many(prefix, ident, max_attempts, window_seconds):
    """Same Redis counters as the web limiter (ratelimit:<prefix>:<ident>), fails open like it."""
    try:
        from app.utils.rate_limit import _get_redis_client
        client = _get_redis_client()
        key = "ratelimit:%s:%s" % (prefix, ident)
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        return count > max_attempts
    except Exception:
        return False


def _mask_email(email):
    name, _, domain = (email or "").partition("@")
    return (name[:1] + "***@" + domain) if domain else "***"


def _tokens_for(candidate):
    claims = {"user_type": "candidate", "organization_id": candidate.organization_id}
    return (
        create_access_token(identity=candidate.id, additional_claims=claims),
        create_refresh_token(identity=candidate.id, additional_claims=claims),
    )


def _gates(candidate):
    """(consent_required, password_change_required) - same rules as candidate_login_required."""
    from app.routes.frontend import _has_current_consent
    consent_required = not _has_current_consent(candidate.id)
    mobile = (candidate.mobile or "").strip()
    pw_required = bool(mobile and candidate.password_hash and check_password_hash(candidate.password_hash, mobile))
    return consent_required, pw_required


def candidate_required(kinds=("candidate",), refresh=False, enforce_gates=True):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            verify_jwt_in_request(refresh=refresh)
            claims = get_jwt()
            if claims.get("user_type") not in kinds:
                return _fail(403, "This token cannot be used here", "wrong token type")
            if refresh or "candidate_otp" in kinds:
                from app.models.revoked_token import RevokedToken
                if RevokedToken.query.filter_by(jti=claims.get("jti")).first():
                    return _fail(401, "This token has already been used", "token reused")
            candidate = Candidate.query.filter_by(id=get_jwt_identity(), is_deleted=False).first()
            if not candidate or candidate.account_status == "blocked":
                return _fail(403, "Your account is unavailable. Please contact your training center.", "account unavailable")
            if enforce_gates:
                consent_required, pw_required = _gates(candidate)
                if consent_required:
                    return _fail(403, "Please accept the privacy notice first", "consent_required")
                if pw_required:
                    return _fail(403, "Please change your default password first", "password_change_required")
            g.candidate = candidate
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def _login_response(candidate, message="Login successful"):
    candidate.last_login_at = datetime.utcnow()
    db.session.commit()
    access_token, refresh_token = _tokens_for(candidate)
    consent_required, pw_required = _gates(candidate)
    return _resp(True, message, {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "candidate": {"registration_number": candidate.registration_number, "full_name": candidate.full_name},
        "consent_required": consent_required,
        "password_change_required": pw_required,
    })


@bp.post("/candidate/login")
def candidate_login():
    from app.routes.frontend import (
        PasswordResetOTP, _client_ip, _generate_otp, _otp_cooldown_remaining, _otp_wait_text,
    )

    payload = request.get_json(silent=True) or {}
    reg_no = (payload.get("registration_number") or "").strip()
    password = payload.get("password") or ""
    if not reg_no or not password:
        return _fail(400, "Registration number and password are required", "missing credentials")

    if _too_many("candidate_api_login", _client_ip(), 5, 300):
        return _fail(429, "Too many attempts. Please try again in a few minutes.", "rate limited")

    candidate = Candidate.query.filter_by(registration_number=reg_no, is_deleted=False).first()
    if not candidate or not candidate.password_hash or not check_password_hash(candidate.password_hash, password):
        return _fail(401, "Invalid registration number or password", "invalid credentials")
    if candidate.account_status == "blocked":
        return _fail(403, "Your account has been blocked. Please contact your training center.", "account blocked")

    if not candidate.email:
        # same as the web: no email on file means no OTP, direct login
        return _login_response(candidate)

    sent = False
    if _otp_cooldown_remaining(candidate.email) <= 0:
        from app.utils.email import send_otp_email
        otp_entry = PasswordResetOTP(
            email=candidate.email, otp_code=_generate_otp(),
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        db.session.add(otp_entry)
        db.session.commit()
        try:
            send_otp_email(candidate.email, otp_entry.otp_code)
            sent = True
        except Exception:
            try:
                otp_entry.is_used = True
                db.session.commit()
            except Exception:
                db.session.rollback()
            return _fail(503, "Could not send OTP email. Please try again later.", "otp email failed")
        message = "An OTP has been sent to your registered email address"
    else:
        wait = _otp_cooldown_remaining(candidate.email)
        message = "An OTP was already sent. Use it, or wait %s before requesting another one." % _otp_wait_text(wait)

    otp_token = create_access_token(
        identity=candidate.id, additional_claims={"user_type": "candidate_otp"},
        expires_delta=timedelta(minutes=OTP_TOKEN_MINUTES),
    )
    return _resp(True, message, {"otp_required": True, "otp_token": otp_token, "email_hint": _mask_email(candidate.email)})


@bp.post("/candidate/verify-otp")
@candidate_required(kinds=("candidate_otp",), enforce_gates=False)
def candidate_verify_otp():
    from app.models.revoked_token import RevokedToken
    from app.routes.frontend import PasswordResetOTP, _client_ip

    candidate = g.candidate
    if not candidate.email:
        return _fail(400, "No email on file", "no email")
    if _too_many("candidate_api_otp", _client_ip(), 5, 600) or _too_many("candidate_api_otp_cand", candidate.id, 5, 600):
        return _fail(429, "Too many attempts. Please try again later.", "rate limited")

    payload = request.get_json(silent=True) or {}
    entered = str(payload.get("otp") or "").strip()
    otp_entry = (
        PasswordResetOTP.query.filter_by(email=candidate.email, otp_code=entered, is_used=False)
        .order_by(PasswordResetOTP.created_at.desc())
        .first()
    )
    if not entered or not otp_entry or not otp_entry.is_valid():
        return _fail(401, "Invalid or expired OTP. Please try again.", "invalid otp")

    otp_entry.is_used = True
    db.session.add(RevokedToken(jti=get_jwt()["jti"], token_type="otp", user_id=candidate.id))
    return _login_response(candidate)


@bp.post("/candidate/refresh")
@candidate_required(refresh=True, enforce_gates=False)
def candidate_refresh():
    """Rotation: the refresh token that was used is revoked, so it works only once."""
    from app.models.revoked_token import RevokedToken

    candidate = g.candidate
    try:
        db.session.add(RevokedToken(jti=get_jwt()["jti"], token_type="refresh", user_id=candidate.id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _fail(401, "This token has already been used", "token reused")
    access_token, refresh_token = _tokens_for(candidate)
    return _resp(True, "Token refreshed", {"access_token": access_token, "refresh_token": refresh_token})


@bp.get("/candidate/consent")
@candidate_required(enforce_gates=False)
def candidate_consent_status():
    from app.routes.frontend import CONSENT_NOTICE_VERSION
    consent_required, _pw = _gates(g.candidate)
    return _resp(True, "OK", {"notice_version": CONSENT_NOTICE_VERSION, "accepted": not consent_required})


@bp.post("/candidate/consent")
@candidate_required(enforce_gates=False)
def candidate_consent_accept():
    from app.models.candidate_consent import CandidateConsent
    from app.routes.frontend import CONSENT_NOTICE_VERSION, _client_ip, _has_current_consent

    candidate = g.candidate
    payload = request.get_json(silent=True) or {}
    if payload.get("agree") is not True:
        return _fail(400, "Consent is required to continue", "agree must be true")
    if not _has_current_consent(candidate.id):
        db.session.add(CandidateConsent(
            candidate_id=candidate.id,
            organization_id=candidate.organization_id,
            notice_version=CONSENT_NOTICE_VERSION,
            consented_at=datetime.utcnow(),
            ip_address=(_client_ip() or "")[:64] or None,
        ))
        db.session.commit()
    return _resp(True, "Your consent has been recorded.", {"accepted": True})


@bp.post("/candidate/change-password")
@candidate_required(enforce_gates=False)
def candidate_change_password():
    candidate = g.candidate
    if _too_many("candidate_api_pw", candidate.id, 5, 900):
        return _fail(429, "Too many attempts. Please try again later.", "rate limited")

    payload = request.get_json(silent=True) or {}
    current = payload.get("current_password") or ""
    new = payload.get("new_password") or ""
    confirm = payload.get("confirm_password") or ""
    mobile = (candidate.mobile or "").strip()

    if not candidate.password_hash or not check_password_hash(candidate.password_hash, current):
        return _fail(400, "Current password is incorrect", "wrong current password")
    if len(new) < 6:
        return _fail(400, "Password must be at least 6 characters long.", "password too short")
    if new != confirm:
        return _fail(400, "Passwords do not match.", "passwords differ")
    if new == current:
        return _fail(400, "New password must be different from the current one.", "same password")
    if mobile and new.strip() == mobile:
        return _fail(400, "Your new password cannot be the same as your mobile number.", "password is mobile")

    candidate.password_hash = generate_password_hash(new)
    db.session.commit()
    return _resp(True, "Password updated.", {"password_change_required": False})


def _iso(value):
    return value.isoformat() if value else None


@bp.get("/candidate/me")
@candidate_required()
def candidate_me():
    from app.models.candidate_placement import CandidatePlacement

    c = g.candidate
    placements = (
        CandidatePlacement.query.filter_by(candidate_id=c.id, status=1)
        .order_by(CandidatePlacement.created_at.desc())
        .all()
    )
    return _resp(True, "OK", {
        "registration_number": c.registration_number,
        "full_name": c.full_name,
        "mobile": c.mobile,
        "email": c.email,
        "training_status": c.training_status,
        "working_status": c.working_status,
        "verification_status": c.verification_status,
        "placements": [
            {
                "job_role": p.job_role,
                "location": p.location,
                "joining_date": _iso(p.joining_date),
                "working_status": p.working_status,
                "exit_date": _iso(p.exit_date),
            }
            for p in placements
        ],
    })


@bp.get("/candidate/salary-slips")
@candidate_required()
def candidate_salary_slips():
    from app.models.salary_slip import SalarySlip

    slips = SalarySlip.query.filter_by(candidate_id=g.candidate.id).order_by(SalarySlip.month.desc()).all()
    return _resp(True, "OK", {
        "current_month": datetime.utcnow().strftime("%Y-%m"),
        "slips": [
            {"id": s.id, "month": s.month, "filename": s.original_filename, "uploaded_at": _iso(s.uploaded_at)}
            for s in slips
        ],
    })


@bp.post("/candidate/salary-slips")
@candidate_required()
def candidate_salary_slip_upload():
    """multipart/form-data: month=YYYY-MM and file. Uses the same function as the web page,
    so type, size, future-month and storage rules are identical."""
    from app.routes.frontend import _create_notification, _save_salary_slip

    candidate = g.candidate
    # same rule as the web page: only after the placement is recorded
    if not candidate.employer_name:
        return _fail(403, "You can upload a salary slip after your placement is recorded.", "no placement recorded")
    month = (request.form.get("month") or "").strip()
    ok, message = _save_salary_slip(candidate, month, request.files.get("file"))
    if not ok:
        return _fail(400, message, "upload rejected")
    try:
        _create_notification(
            title="Salary slip uploaded: %s" % candidate.full_name,
            message="%s uploaded the salary slip for %s." % (candidate.full_name, month),
            notif_type="info",
            organization_id=candidate.organization_id,
            candidate_id=candidate.id,
        )
    except Exception:
        pass  # the slip is saved; a notification problem must not fail the upload
    return _resp(True, message, {"month": month}, None, 201)


@bp.get("/candidate/salary-slips/<slip_id>/download")
@candidate_required()
def candidate_salary_slip_download(slip_id):
    from app.routes.frontend import _send_salary_slip
    return _send_salary_slip(g.candidate, slip_id)