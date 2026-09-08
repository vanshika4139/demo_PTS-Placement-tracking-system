"""
Integration tests hitting real routes.

SAFETY: this file never lets a write actually succeed against the real
database. The "blocked" test intentionally fails to create anything (that
IS the point of the test); we never test the "allowed" path via a real
HTTP write, since that would insert a permanent row into your live batches
table. That path is already verified manually through the UI.
"""

from tests.conftest import login_as


def test_unauthenticated_user_is_redirected_away(client):
    response = client.get("/organization/candidates", follow_redirects=False)
    assert response.status_code in (301, 302), "Anonymous users should be redirected, not shown the page"


def test_super_admin_can_reach_super_admin_dashboard(client):
    login_as(client, {
        "id": "test-super-admin",
        "is_super_admin": True,
        "full_name": "Test Super Admin",
        "email": "test-super-admin@example.com",
        "organization_id": None,
    })
    response = client.get("/super-admin/dashboard")
    assert response.status_code == 200


def test_user_with_no_permissions_is_blocked_from_creating_a_batch(client):
    login_as(client, {
        "id": "test-no-permissions-user",
        "is_super_admin": False,
        "full_name": "No Permissions",
        "email": "test-no-permissions@example.com",
        "organization_id": 1,
    })
    # follow_redirects=False - we only care that the write was blocked
    # (a redirect), not where it lands afterwards. This also avoids any
    # possible redirect loop for a user with zero permissions.
    response = client.post(
        "/organization/batches/create",
        data={"name": "Should Not Be Created", "training_center": "Test"},
        follow_redirects=False,
    )
    assert response.status_code == 302, "A user with no batch.create permission must be redirected, not allowed through"


def test_roles_permissions_page_requires_super_admin(client):
    login_as(client, {
        "id": "test-regular-user",
        "is_super_admin": False,
        "full_name": "Regular User",
        "email": "test-regular@example.com",
        "organization_id": 1,
    })
    response = client.get("/super-admin/roles-permissions", follow_redirects=False)
    assert response.status_code in (301, 302, 403), "Non-super-admins must not reach the Roles & Permissions screen"