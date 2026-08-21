def test_login_valid_credentials(client, admin_user):
    response = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "admin@test.com"


def test_login_wrong_password(client, admin_user):
    response = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "wrong"})
    assert response.status_code == 401


def test_login_unknown_email(client):
    response = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "anything"})
    assert response.status_code == 401


def test_logout_requires_auth(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 403


def test_logout_with_valid_token(client, auth_headers):
    response = client.post("/api/auth/logout", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "logged out"


# ── Admin impersonation (testing aid) ─────────────────────────────────────────

def test_admin_can_impersonate_user(client, db, admin_user, auth_headers):
    from app.models.user import User
    from app.utils.password import hash_password
    from uuid import uuid4

    target = User(
        email=f"impersonated-{uuid4().hex[:8]}@permtests.com",
        name="Impersonation Target",
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=True,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    r = client.post(f"/api/auth/impersonate/{target.id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == target.email

    # The issued token acts as the target user — reading their own record
    # (self-read is always allowed, see users.get_user) proves it.
    imp_headers = {"Authorization": f"Bearer {body['access_token']}"}
    ctx = client.get(f"/api/users/{target.id}", headers=imp_headers)
    assert ctx.status_code == 200
    assert ctx.json()["email"] == target.email


def test_non_admin_cannot_impersonate(client, db, admin_user, auth_headers):
    from app.models.user import User
    from app.utils.password import hash_password
    from uuid import uuid4

    pleb = User(
        email=f"pleb-{uuid4().hex[:8]}@permtests.com",
        name="Not Admin",
        password_hash=hash_password("password123"),
        role="manager",
        is_active=True,
    )
    db.add(pleb)
    db.commit()
    db.refresh(pleb)

    login = client.post("/api/auth/login", json={"email": pleb.email, "password": "password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = client.post(f"/api/auth/impersonate/{admin_user.id}", headers=headers)
    assert r.status_code == 403
