def test_list_users_requires_admin(client, admin_user):
    # No auth
    response = client.get("/api/users")
    assert response.status_code == 403


def test_list_users_as_admin(client, admin_user, auth_headers):
    response = client.get("/api/users", headers=auth_headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert any(u["email"] == "admin@test.com" for u in users)


def test_create_user(client, admin_user, auth_headers):
    response = client.post(
        "/api/users",
        json={"email": "new@test.com", "name": "New User", "password": "pass123", "role": "instructor"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["email"] == "new@test.com"


def test_create_duplicate_email(client, admin_user, auth_headers):
    payload = {"email": "dup@test.com", "name": "Dup", "password": "pass123", "role": "instructor"}
    client.post("/api/users", json=payload, headers=auth_headers)
    response = client.post("/api/users", json=payload, headers=auth_headers)
    assert response.status_code == 400


def test_get_user_by_id(client, admin_user, auth_headers):
    """The bare by-id read (`GET /api/users/{id}`) had no coverage anywhere in
    the suite outside its `/pin` sub-route. Basic happy path: an authorized
    caller (here, an admin) reading a user they're allowed to see."""
    response = client.get(f"/api/users/{admin_user.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(admin_user.id)
    assert response.json()["email"] == "admin@test.com"


def test_update_user(client, admin_user, auth_headers):
    response = client.put(
        f"/api/users/{admin_user.id}",
        json={"name": "Updated Name"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_delete_user_soft(client, admin_user, auth_headers, db):
    from app.models.user import User as UserModel
    response = client.delete(f"/api/users/{admin_user.id}", headers=auth_headers)
    assert response.status_code == 200
    db.expire(admin_user)
    db.refresh(admin_user)
    assert admin_user.is_active == False


def test_recreate_revives_deleted_instructor(client, admin_user, auth_headers, db):
    """Delete is a soft delete, so re-adding the same email must revive the SAME
    account (not error, not duplicate) — otherwise the email is locked forever."""
    from app.models.user import User as UserModel
    created = client.post(
        "/api/users",
        json={"email": "revive@test.com", "name": "Original", "password": "pass123", "role": "instructor"},
        headers=auth_headers,
    ).json()
    original_id = created["id"]
    assert client.delete(f"/api/users/{original_id}", headers=auth_headers).status_code == 200

    revived = client.post(
        "/api/users",
        json={"email": "revive@test.com", "name": "Revived", "password": "newpass", "role": "manager"},
        headers=auth_headers,
    )
    assert revived.status_code == 201
    body = revived.json()
    assert body["id"] == original_id      # same row revived, not a new account
    assert body["is_active"] is True
    assert body["name"] == "Revived"      # details refreshed from the new payload
    assert body["role"] == "manager"

    # Exactly one row for that email — no duplicate was created.
    assert db.query(UserModel).filter(UserModel.email == "revive@test.com").count() == 1


def test_recreate_revive_resets_onboarding_state(client, admin_user, auth_headers, db):
    """A revived account is a clean slate: stale invite/PIN state is cleared so a
    fresh invite works and no old shared-device PIN carries over."""
    from datetime import datetime
    from app.models.user import User as UserModel
    created = client.post(
        "/api/users",
        json={"email": "stale@test.com", "name": "Stale", "password": "pass123", "role": "instructor"},
        headers=auth_headers,
    ).json()
    row = db.query(UserModel).filter(UserModel.id == created["id"]).first()
    row.invite_sent_at = datetime.utcnow()
    row.password_set_at = datetime.utcnow()
    row.pin, row.pin_hash = "1234", "x"
    db.commit()
    assert client.delete(f"/api/users/{created['id']}", headers=auth_headers).status_code == 200

    client.post(
        "/api/users",
        json={"email": "stale@test.com", "name": "Fresh", "password": "pass123", "role": "instructor"},
        headers=auth_headers,
    )
    db.expire(row)
    db.refresh(row)
    assert row.is_active is True
    assert row.invite_sent_at is None
    assert row.password_set_at is None
    assert row.pin is None and row.pin_hash is None


def test_active_email_still_conflicts(client, admin_user, auth_headers):
    """Reuse only applies to deactivated accounts — an ACTIVE email still 400s."""
    payload = {"email": "active@test.com", "name": "Active", "password": "pass123", "role": "instructor"}
    assert client.post("/api/users", json=payload, headers=auth_headers).status_code == 201
    payload["name"] = "Second"
    assert client.post("/api/users", json=payload, headers=auth_headers).status_code == 400


def test_create_instructor_without_email(client, admin_user, auth_headers, db):
    """A PIN-only instructor can be created with no email at all."""
    from app.models.user import User as UserModel
    resp = client.post(
        "/api/users",
        json={"name": "PIN Only", "role": "instructor"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] is None
    assert body["role"] == "instructor"
    assert db.query(UserModel).filter(UserModel.id == body["id"]).first().email is None


def test_multiple_instructors_without_email_coexist(client, admin_user, auth_headers):
    """NULL emails are distinct under the unique index — many can coexist."""
    a = client.post("/api/users", json={"name": "No Email A", "role": "instructor"}, headers=auth_headers)
    b = client.post("/api/users", json={"name": "No Email B", "role": "instructor"}, headers=auth_headers)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_invite_rejected_for_user_without_email(client, admin_user, auth_headers):
    """You can't send a setup email to someone who has no email."""
    created = client.post("/api/users", json={"name": "No Email", "role": "instructor"}, headers=auth_headers).json()
    resp = client.post("/api/auth/invite", json={"user_id": created["id"]}, headers=auth_headers)
    assert resp.status_code == 400
