import pytest
from app import create_app
from app.extensions import db
from app.models import Organization, Permission, Role, User, RolePermission, UserRole
from app.utils.security import hash_password


@pytest.fixture()
def app():
    app = create_app("testing")

    db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert db_uri.startswith("sqlite:///:memory:"), (
        f"Refusing to run tests against non-sqlite database: {db_uri!r}. "
        "Check app/config/testing.py — it must never point at a real database."
    )

    with app.app_context():
        db.drop_all()
        db.create_all()

        organization = Organization(
            organization_code="ACME-ORG",
            organization_name="Acme Org",
            status=1,
        )
        organization.id = 1
        db.session.add(organization)
        db.session.flush()

        permission = Permission(code="organization.manage", description="Manage organizations")
        permission.id = 1
        db.session.add(permission)
        db.session.flush()

        permission2 = Permission(code="candidate.create", description="Create candidates")
        permission2.id = 2
        db.session.add(permission2)
        db.session.flush()

        role = Role(name="SUPER_ADMIN", code="SUPER_ADMIN", organization_id=None)
        role.id = 1
        db.session.add(role)
        db.session.flush()

        role_permission1 = RolePermission(role_id=role.id, permission_id=permission.id)
        db.session.add(role_permission1)
        db.session.flush()

        role_permission2 = RolePermission(role_id=role.id, permission_id=permission2.id)
        db.session.add(role_permission2)
        db.session.flush()

        user = User(
            email="super@example.com",
            password_hash=hash_password("StrongPass123!"),
            full_name="Super Admin",
            organization_id=None,
            is_super_admin=True,
            is_active=True,
        )
        user.id = 1
        db.session.add(user)
        db.session.flush()

        user_role = UserRole(user_id=user.id, role_id=role.id)
        db.session.add(user_role)
        db.session.flush()

        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_login_returns_tokens_and_user_profile(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "super@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["access_token"]
    assert payload["data"]["refresh_token"]
    assert payload["data"]["user"]["email"] == "super@example.com"


def test_permission_required_allows_super_admin(client):
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "super@example.com", "password": "StrongPass123!"},
    )
    token = login_response.get_json()["data"]["access_token"]
    response = client.get(
        "/api/v1/auth/permissions-check",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["allowed"] is True