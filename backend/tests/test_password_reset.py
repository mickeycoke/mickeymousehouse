from app.models.user import User
from app.utils.password import hash_password, verify_password
from app.utils.tokens import create_reset_token


def _user(db, email="reset-flow@test.com", password="orig-pw-123"):
    u = User(email=email, name="Reset Flow", password_hash=hash_password(password),
             role="instructor", is_active=True)
    db.add(u)
    db.flush()
    return u


def test_forgot_password_known_and_unknown_email_return_identical_response(client, db):
    _user(db, "known-reset@test.com")

    known = client.post("/api/auth/forgot-password", json={"email": "known-reset@test.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "no-such-user@test.com"})

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == {"sent": True}
    assert known.json() == unknown.json()


def test_forgot_password_rejects_malformed_email(client):
    resp = client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
    assert resp.status_code == 422


def test_forgot_password_email_send_failure_does_not_leak_or_500(client, db, monkeypatch):
    """send_email() raises on provider failure — a transient SMTP hiccup must
    still return the same generic {sent: true}, not a 500 that only matching
    emails could produce."""
    _user(db, "flaky-smtp@test.com")

    def _boom(*args, **kwargs):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr("app.services.email.send_reset_password_email", _boom)

    resp = client.post("/api/auth/forgot-password", json={"email": "flaky-smtp@test.com"})
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}


def test_forgot_password_sends_email_via_background_task_for_matched_user(client, db, monkeypatch):
    """Confirms the email is actually scheduled/sent (not just silently
    dropped) now that it runs via BackgroundTasks rather than inline — the
    TestClient runs background tasks before returning, so this call site is
    observable synchronously in the test."""
    user = _user(db, "bg-task-reset@test.com")
    calls = []
    monkeypatch.setattr(
        "app.services.email.send_reset_password_email",
        lambda to, name, token: calls.append((to, name, token)),
    )

    resp = client.post("/api/auth/forgot-password", json={"email": "bg-task-reset@test.com"})
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == user.email
    assert calls[0][1] == user.name


def test_forgot_password_repeated_requests_for_same_user_are_cooled_down(client, db, monkeypatch):
    """A per-user in-memory cooldown caps outbound email volume — repeated
    requests for one known email must not each trigger a real send (inbox-
    flooding / shared-provider-quota exhaustion), while still returning the
    identical generic response every time."""
    _user(db, "cooldown-reset@test.com")
    calls = []
    monkeypatch.setattr(
        "app.services.email.send_reset_password_email",
        lambda to, name, token: calls.append((to, name, token)),
    )

    first = client.post("/api/auth/forgot-password", json={"email": "cooldown-reset@test.com"})
    second = client.post("/api/auth/forgot-password", json={"email": "cooldown-reset@test.com"})

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == {"sent": True} == second.json()
    assert len(calls) == 1


def test_reset_password_info_rejects_invalid_token(client):
    resp = client.get("/api/auth/reset-password/not-a-real-token")
    assert resp.status_code == 400
    assert "not valid" in resp.json()["detail"]


def test_reset_password_info_rejects_expired_token(client, db, monkeypatch):
    user = _user(db, "expired-reset@test.com")
    monkeypatch.setattr("app.utils.tokens.RESET_EXPIRE_MINUTES", -5)
    token = create_reset_token(str(user.id))

    resp = client.get(f"/api/auth/reset-password/{token}")
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]


def test_reset_password_full_flow_logs_in_and_replaces_password(client, db):
    user = _user(db, "full-flow-reset@test.com", "original-pw-123")
    token = create_reset_token(str(user.id))

    info = client.get(f"/api/auth/reset-password/{token}")
    assert info.status_code == 200
    assert info.json() == {"valid": True, "name": "Reset Flow", "email": "full-flow-reset@test.com"}

    done = client.post("/api/auth/reset-password", json={"token": token, "password": "brand-new-pw-456"})
    assert done.status_code == 200
    body = done.json()
    assert body["access_token"]
    assert body["user"]["email"] == "full-flow-reset@test.com"

    db.refresh(user)
    assert verify_password("brand-new-pw-456", user.password_hash)
    assert not verify_password("original-pw-123", user.password_hash)

    old_login = client.post("/api/auth/login", json={"email": "full-flow-reset@test.com", "password": "original-pw-123"})
    assert old_login.status_code == 401
    new_login = client.post("/api/auth/login", json={"email": "full-flow-reset@test.com", "password": "brand-new-pw-456"})
    assert new_login.status_code == 200


def test_reset_password_rejects_short_password(client, db):
    user = _user(db, "short-reset-pw@test.com")
    token = create_reset_token(str(user.id))
    resp = client.post("/api/auth/reset-password", json={"token": token, "password": "short"})
    assert resp.status_code == 422


def test_reset_password_token_cannot_be_replayed(client, db):
    user = _user(db, "replay-reset@test.com")
    token = create_reset_token(str(user.id))

    first = client.post("/api/auth/reset-password", json={"token": token, "password": "first-new-pw-1"})
    assert first.status_code == 200

    replay = client.post("/api/auth/reset-password", json={"token": token, "password": "second-new-pw-2"})
    assert replay.status_code == 400
    assert "already been used" in replay.json()["detail"]


def test_reset_password_rejects_inactive_user_token(client, db):
    user = _user(db, "inactive-reset@test.com")
    token = create_reset_token(str(user.id))
    user.is_active = False
    db.flush()

    resp = client.post("/api/auth/reset-password", json={"token": token, "password": "whatever-pw-1"})
    assert resp.status_code == 400
    assert "not valid" in resp.json()["detail"]
