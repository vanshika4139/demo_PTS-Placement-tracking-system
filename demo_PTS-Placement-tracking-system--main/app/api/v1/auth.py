from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required

from app.extensions import db
from app.models import Organization, Permission, Role, RolePermission, User, UserRole
from app.permissions import permission_required
from app.utils.security import hash_password, verify_password

bp = Blueprint("auth", __name__)


def _check_password(password, stored):
    """The web app stores Werkzeug hashes; older/seeded accounts may hold bcrypt.
    Accept both, and never raise on an unknown hash format (that was a 500)."""
    from werkzeug.security import check_password_hash
    stored = stored or ""
    try:
        if stored.startswith("$2"):
            return verify_password(password, stored)
        return check_password_hash(stored, password)
    except ValueError:
        return False


@bp.post("/auth/login")
def login():
    from datetime import datetime
    from app.models.login_history import LoginHistory
    from app.routes.frontend import _client_ip, _ip_allowed, _device_hash, EMPLOYER_PORTAL_ENABLED

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")

    def _fail(status, message, detail):
        return jsonify({"success": False, "message": message, "data": None, "errors": {"detail": detail}, "meta": {}}), status

    if not email or not password:
        return _fail(400, "Email and password are required", "missing credentials")

    ip = _client_ip()
    ua = request.headers.get("User-Agent", "")[:500]
    user = User.query.filter_by(email=email, is_deleted=False).first()

    def _record(success, reason=None):
        db.session.add(LoginHistory(
            email=email,
            full_name=user.full_name if user else None,
            user_id=user.id if user else None,
            ip_address=ip,
            user_agent=ua,
            device_hash=_device_hash(ua),
            success=success,
            failure_reason=reason,
        ))
        db.session.commit()

    if not user or not _check_password(password, user.password_hash):
        _record(False, "Invalid credentials")
        return _fail(401, "Invalid credentials", "invalid credentials")

    if not user.is_active:
        _record(False, "Account inactive")
        return _fail(403, "Account inactive", "inactive account")

    if not _ip_allowed(user, ip):
        _record(False, "IP not allowed")
        return _fail(403, "Login is not allowed from this network", "ip not allowed")

    if getattr(user, "employer_id", None) and not EMPLOYER_PORTAL_ENABLED:
        _record(False, "Employer login on hold")
        return _fail(403, "Employer login is on hold", "employer login on hold")

    if not user.is_super_admin and user.organization_id:
        organization = Organization.query.get(user.organization_id)
        if organization and organization.status == 0:
            _record(False, "Organization suspended")
            return _fail(403, "Your organization's access has been suspended", "organization suspended")

    user.last_login_at = datetime.utcnow()
    _record(True)

    access_token = create_access_token(identity=str(user.id), additional_claims={"email": user.email, "is_super_admin": user.is_super_admin, "organization_id": user.organization_id})
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify(
        {
            "success": True,
            "message": "Login successful",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {"id": user.public_id, "email": user.email, "full_name": user.full_name, "is_super_admin": user.is_super_admin},
            },
            "errors": None,
            "meta": {},
        }
    )


@bp.get("/auth/permissions-check")
@jwt_required()
@permission_required("candidate.create")
def permissions_check():
    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user:
        return jsonify({"success": False, "message": "User not found", "data": None, "errors": {"detail": "user not found"}, "meta": {}}), 404

    return jsonify(
        {
            "success": True,
            "message": "Permission check passed",
            "data": {"allowed": True, "user_id": user.public_id},
            "errors": None,
            "meta": {},
        }
    )
