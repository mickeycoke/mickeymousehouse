from app.models.user import User
from app.utils.password import hash_password, verify_password


def _invitee(db, email="invitee@test.com"):
    u = User(email=email, name="Invitee", password_hash=hash_password("unusable"),
             role="instructor", is_active=True)
    db.add(u)
    db.flush()
    return u


def _token_from_link(link):
    return link.split("token=", 1)[1]


def test_invite_validate_set_password_and_login(client, auth_headers, db, admin_user):
    user = _invitee(db, "invite-flow@test.com")

    # 1) admin sends the invite; console backend returns the link for dev/test
    resp = client.post("/api/auth/invite", headers=auth_headers, json={"user_id": str(user.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is True and body["invite_link"]
    token = _token_from_link(body["invite_link"])

    # 2) the link validates before showing the form
    info = client.get(f"/api/auth/invite/{token}")
    assert info.status_code == 200
    assert info.json() == {"valid": True, "name": "Invitee", "email": "invite-flow@test.com"}

    # 3) setting the password logs them in
    done = client.post("/api/auth/set-password", json={"token": token, "password": "s3cret-pw"})
    assert done.status_code == 200
    assert done.json()["access_token"]
    db.refresh(user)
    assert user.password_set_at is not None
    assert verify_password("s3cret-pw", user.password_hash)

    # 4) the same link cannot be replayed
    replay = client.post("/api/auth/set-password", json={"token": token, "password": "another-pw"})
    assert replay.status_code == 400
    assert "already been used" in replay.json()["detail"]


def test_set_password_rejects_short_password(client, auth_headers, db, admin_user):
    user = _invitee(db, "short-pw@test.com")
    link = client.post("/api/auth/invite", headers=auth_headers,
                       json={"user_id": str(user.id)}).json()["invite_link"]
    resp = client.post("/api/auth/set-password",
                       json={"token": _token_from_link(link), "password": "short"})
    assert resp.status_code == 422  # min_length=8


def test_invalid_token_rejected(client):
    resp = client.get("/api/auth/invite/not-a-real-token")
    assert resp.status_code == 400
    assert "not valid" in resp.json()["detail"]


def test_studio_owner_can_invite_own_instructor(client, db):
    from app.models.studio import Studio
    from app.models.studio_owner import StudioOwner
    studio = Studio(name="Owner Invite Studio", display_name="Owner Invite Studio", is_active=True)
    db.add(studio)
    db.flush()
    owner = User(email="si-owner@test.com", name="Owner", password_hash=hash_password("pw12345"),
                 role="instructor", is_active=True)
    instr = User(email="si-instr@test.com", name="Instr", password_hash=hash_password("x"),
                 role="instructor", studio_id=studio.id, is_active=True)
    db.add_all([owner, instr])
    db.flush()
    db.add(StudioOwner(user_id=owner.id, studio_id=studio.id, level="owner", is_active=True))
    db.flush()
    token = client.post("/api/auth/login",
                        json={"email": "si-owner@test.com", "password": "pw12345"}).json()["access_token"]
    resp = client.post("/api/auth/invite", headers={"Authorization": f"Bearer {token}"},
                       json={"user_id": str(instr.id)})
    assert resp.status_code == 200 and resp.json()["sent"] is True


def test_non_manager_cannot_invite(client, db):
    from app.utils.password import hash_password as hp
    stranger = User(email="not-a-manager@test.com", name="Stranger",
                    password_hash=hp("pw12345"), role="instructor", is_active=True)
    target = _invitee(db, "target-x@test.com")
    db.add(stranger)
    db.flush()
    token = client.post("/api/auth/login",
                        json={"email": "not-a-manager@test.com", "password": "pw12345"}).json()["access_token"]
    resp = client.post("/api/auth/invite", headers={"Authorization": f"Bearer {token}"},
                       json={"user_id": str(target.id)})
    assert resp.status_code == 403
