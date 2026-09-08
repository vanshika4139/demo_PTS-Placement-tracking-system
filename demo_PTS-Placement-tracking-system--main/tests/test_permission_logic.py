"""
Tests the core permission-checking logic in app/utils/permissions.py:
Super Admin bypass > user-specific override > role permission > deny.

SAFETY: every row this file inserts is deleted in the same test's
fixture teardown, via a try/finally-equivalent (pytest yield-fixture).
Nothing here ever touches the database schema.
"""

import uuid

import pytest

from app.extensions import db
from app.models import Role, Permission, RolePermission, UserRole, UserPermissionOverride, User
from app.utils.permissions import has_permission, get_user_permission_codes, invalidate_user_permission_cache


def _new_id():
    return str(uuid.uuid4()).replace("-", "")


@pytest.fixture()
def temp_role_with_permission(app):
    """Creates ONE throwaway role + ONE throwaway permission + ONE throwaway
    user (a real row, since user_roles.user_id has a foreign key to users.id)
    and links the user to the role. Deletes exactly those rows afterwards,
    even if the test fails or raises."""
    with app.app_context():
        role = Role(id=_new_id(), name="_pytest_role", code=f"_pytest_role_{_new_id()[:8]}")
        perm = Permission(id=_new_id(), code=f"_pytest.permission_{_new_id()[:8]}", description="pytest temp permission")
        db.session.add_all([role, perm])
        db.session.flush()

        fake_user_id = _new_id()
        temp_user = User(
            id=fake_user_id,
            email=f"_pytest_{fake_user_id[:8]}@test.local",
            password_hash="not-a-real-hash-just-for-tests",
            full_name="Pytest Temp User",
            is_super_admin=False,
            is_active=True,
        )
        db.session.add(temp_user)
        db.session.add(RolePermission(id=_new_id(), role_id=role.id, permission_id=perm.id))
        db.session.add(UserRole(id=_new_id(), user_id=fake_user_id, role_id=role.id))
        db.session.commit()

        role_id, perm_id = role.id, perm.id  # capture before session objects go stale

        try:
            yield {"role_id": role_id, "permission_code": perm.code, "permission_id": perm_id, "user_id": fake_user_id}
        finally:
            UserRole.query.filter_by(user_id=fake_user_id).delete()
            RolePermission.query.filter_by(role_id=role_id).delete()
            UserPermissionOverride.query.filter_by(user_id=fake_user_id).delete()
            User.query.filter_by(id=fake_user_id).delete()
            Role.query.filter_by(id=role_id).delete()
            Permission.query.filter_by(id=perm_id).delete()
            db.session.commit()
            invalidate_user_permission_cache(fake_user_id)


def test_super_admin_bypasses_all_checks(app):
    with app.app_context():
        session_user = {"id": "irrelevant-id", "is_super_admin": True}
        assert has_permission(session_user, "any.permission.that.does.not.exist") is True


def test_user_with_no_role_has_no_permissions(app):
    with app.app_context():
        session_user = {"id": _new_id(), "is_super_admin": False}
        assert has_permission(session_user, "some.random.permission") is False


def test_role_permission_is_granted_through_role(app, temp_role_with_permission):
    with app.app_context():
        data = temp_role_with_permission
        invalidate_user_permission_cache(data["user_id"])
        codes = get_user_permission_codes(data["user_id"])
        assert data["permission_code"] in codes


def test_override_can_deny_a_permission_the_role_grants(app, temp_role_with_permission):
    with app.app_context():
        data = temp_role_with_permission
        override = UserPermissionOverride(
            id=_new_id(), user_id=data["user_id"], permission_id=data["permission_id"], is_allowed=False
        )
        db.session.add(override)
        db.session.commit()
        invalidate_user_permission_cache(data["user_id"])

        codes = get_user_permission_codes(data["user_id"])
        assert data["permission_code"] not in codes, "Override should DENY even though the role grants it"


def test_override_can_grant_a_permission_the_role_does_not_have(app, temp_role_with_permission):
    with app.app_context():
        data = temp_role_with_permission

        extra_perm = Permission(id=_new_id(), code=f"_pytest.extra_{_new_id()[:8]}", description="pytest temp, not in the role")
        db.session.add(extra_perm)
        db.session.commit()

        try:
            codes_before = get_user_permission_codes(data["user_id"])
            assert extra_perm.code not in codes_before

            override = UserPermissionOverride(
                id=_new_id(), user_id=data["user_id"], permission_id=extra_perm.id, is_allowed=True
            )
            db.session.add(override)
            db.session.commit()
            invalidate_user_permission_cache(data["user_id"])

            codes_after = get_user_permission_codes(data["user_id"])
            assert extra_perm.code in codes_after
        finally:
            UserPermissionOverride.query.filter_by(user_id=data["user_id"], permission_id=extra_perm.id).delete()
            Permission.query.filter_by(id=extra_perm.id).delete()
            db.session.commit()