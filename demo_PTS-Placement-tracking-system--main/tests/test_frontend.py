from app import create_app


def test_login_page_renders():
    app = create_app("testing")
    client = app.test_client()
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Codevocado" in response.data


def test_role_dashboard_pages_redirect_when_not_logged_in():
    app = create_app("testing")
    client = app.test_client()
    for path in ["/super-admin/dashboard", "/organization/dashboard", "/candidate/dashboard"]:
        response = client.get(path)
        # Unauthenticated users must be redirected (302), not shown the dashboard directly.
        assert response.status_code == 302