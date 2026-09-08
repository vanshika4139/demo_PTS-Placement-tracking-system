from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required

from app.extensions import db
from app.models import Organization, Permission, Role, RolePermission, User, UserRole
from app.permissions import permission_required
from app.utils.security import hash_password, verify_password

bp = Blueprint("auth", __name__)


@bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")
    password = payload.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required", "data": None, "errors": {"detail": "missing credentials"}, "meta": {}}), 400

    user = User.query.filter_by(email=email, is_deleted=False).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"success": False, "message": "Invalid credentials", "data": None, "errors": {"detail": "invalid credentials"}, "meta": {}}), 401

    if not user.is_active:
        return jsonify({"success": False, "message": "Account inactive", "data": None, "errors": {"detail": "inactive account"}, "meta": {}}), 403

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
