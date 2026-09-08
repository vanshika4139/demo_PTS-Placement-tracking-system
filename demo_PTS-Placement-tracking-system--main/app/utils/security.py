from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, get_current_user
from passlib.hash import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.verify(password, hashed_password)


def create_tokens(user) -> dict:
    access_token = create_access_token(identity=str(user.id), additional_claims={"email": user.email, "is_super_admin": user.is_super_admin, "organization_id": user.organization_id})
    refresh_token = create_refresh_token(identity=str(user.id))
    return {"access_token": access_token, "refresh_token": refresh_token}


def issue_tokens(user) -> dict:
    return create_tokens(user)


def get_current_user_from_context() -> object | None:
    return get_current_user()
