"""Phase 2/3: invite status (invited/accepted) on the studio-owner and
franchise-owner list responses, plus the "send setup email" action they
drive. Reuses the Phase 0 /api/auth/invite + /api/auth/set-password
endpoints — this file only covers the new derived fields and the UI action
built on top of them.
"""
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password


def _make_user(db, email, name):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        db.query(StudioOwner).filter(StudioOwner.user_id == existing.id).delete()
        db.query(FranchiseOwner).filter(FranchiseOwner.user_id == existing.id).delete()
        db.delete(existing)
        db.commit()
    user = User(
        email=email,
        name=name,
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_studio(db, name):
    studio = Studio(name=name, display_name=name, is_active=True)
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


def _make_franchise(db, name):
    franchise = Franchise(name=name, is_active=True)
    db.add(franchise)
    db.commit()
    db.refresh(franchise)
    return franchise


def _extract_token(invite_link):
    assert invite_link and "token=" in invite_link
    return invite_link.split("token=", 1)[1]


# ── Studio owners ──────────────────────────────────────────────────────────

def test_studio_owner_list_defaults_to_not_invited(client, auth_headers, db):
    owner = _make_user(db, "invite-studio-owner-1@test.com", "Invite Studio Owner 1")
    studio = _make_studio(db, "Invite Status Studio 1")

    assign = client.post(
        "/api/studio-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "studio_id": str(studio.id)},
    )
    assert assign.status_code == 201
    assert assign.json()["invited"] is False
    assert assign.json()["accepted"] is False

    listing = client.get(f"/api/studio-owners?studio_id={studio.id}", headers=auth_headers)
    assert listing.status_code == 200
    row = next(r for r in listing.json() if r["user_id"] == str(owner.id))
    assert row["invited"] is False
    assert row["accepted"] is False


def test_studio_owner_invite_marks_invited_then_accepted(client, auth_headers, db):
    owner = _make_user(db, "invite-studio-owner-2@test.com", "Invite Studio Owner 2")
    studio = _make_studio(db, "Invite Status Studio 2")

    client.post(
        "/api/studio-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "studio_id": str(studio.id)},
    )

    invite_resp = client.post("/api/auth/invite", headers=auth_headers, json={"user_id": str(owner.id)})
    assert invite_resp.status_code == 200
    body = invite_resp.json()
    assert body["sent"] is True
    assert body["email"] == owner.email
    invite_link = body["invite_link"]  # populated in dev (console email backend)

    listing = client.get(f"/api/studio-owners?studio_id={studio.id}", headers=auth_headers)
    row = next(r for r in listing.json() if r["user_id"] == str(owner.id))
    assert row["invited"] is True
    assert row["accepted"] is False

    token = _extract_token(invite_link)
    set_pw = client.post("/api/auth/set-password", json={"token": token, "password": "newpassword1"})
    assert set_pw.status_code == 200

    listing_after = client.get(f"/api/studio-owners?studio_id={studio.id}", headers=auth_headers)
    row_after = next(r for r in listing_after.json() if r["user_id"] == str(owner.id))
    assert row_after["invited"] is True
    assert row_after["accepted"] is True


def test_studio_owner_list_batches_multiple_owner_statuses_correctly(client, auth_headers, db):
    """Several owners on the same studio, in different invite states — the
    shared _with_user_labels batched user lookup must attribute invited/
    accepted to the right row, not just the first/last one."""
    studio = _make_studio(db, "Invite Status Studio 3")

    not_invited = _make_user(db, "invite-studio-owner-3a@test.com", "Not Invited")
    invited_only = _make_user(db, "invite-studio-owner-3b@test.com", "Invited Only")
    accepted = _make_user(db, "invite-studio-owner-3c@test.com", "Accepted")

    for u in (not_invited, invited_only, accepted):
        r = client.post(
            "/api/studio-owners",
            headers=auth_headers,
            json={"user_id": str(u.id), "studio_id": str(studio.id)},
        )
        assert r.status_code == 201

    invite_resp = client.post("/api/auth/invite", headers=auth_headers, json={"user_id": str(invited_only.id)})
    assert invite_resp.status_code == 200

    invite_resp2 = client.post("/api/auth/invite", headers=auth_headers, json={"user_id": str(accepted.id)})
    assert invite_resp2.status_code == 200
    token = _extract_token(invite_resp2.json()["invite_link"])
    assert client.post("/api/auth/set-password", json={"token": token, "password": "newpassword1"}).status_code == 200

    listing = client.get(f"/api/studio-owners?studio_id={studio.id}", headers=auth_headers).json()
    by_user = {row["user_id"]: row for row in listing}

    assert by_user[str(not_invited.id)]["invited"] is False
    assert by_user[str(not_invited.id)]["accepted"] is False

    assert by_user[str(invited_only.id)]["invited"] is True
    assert by_user[str(invited_only.id)]["accepted"] is False

    assert by_user[str(accepted.id)]["invited"] is True
    assert by_user[str(accepted.id)]["accepted"] is True


# ── Franchise owners ───────────────────────────────────────────────────────

def test_franchise_owner_list_defaults_to_not_invited(client, auth_headers, db):
    owner = _make_user(db, "invite-franchise-owner-1@test.com", "Invite Franchise Owner 1")
    franchise = _make_franchise(db, "Invite Status Franchise 1")

    assign = client.post(
        "/api/franchise-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "franchise_id": str(franchise.id)},
    )
    assert assign.status_code == 201
    assert assign.json()["invited"] is False
    assert assign.json()["accepted"] is False

    listing = client.get(f"/api/franchise-owners?franchise_id={franchise.id}", headers=auth_headers)
    row = next(r for r in listing.json() if r["user_id"] == str(owner.id))
    assert row["invited"] is False
    assert row["accepted"] is False


def test_franchise_owner_invite_marks_invited_then_accepted(client, auth_headers, db):
    owner = _make_user(db, "invite-franchise-owner-2@test.com", "Invite Franchise Owner 2")
    franchise = _make_franchise(db, "Invite Status Franchise 2")

    client.post(
        "/api/franchise-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "franchise_id": str(franchise.id)},
    )

    invite_resp = client.post("/api/auth/invite", headers=auth_headers, json={"user_id": str(owner.id)})
    assert invite_resp.status_code == 200
    invite_link = invite_resp.json()["invite_link"]

    listing = client.get(f"/api/franchise-owners?franchise_id={franchise.id}", headers=auth_headers)
    row = next(r for r in listing.json() if r["user_id"] == str(owner.id))
    assert row["invited"] is True
    assert row["accepted"] is False

    token = _extract_token(invite_link)
    assert client.post("/api/auth/set-password", json={"token": token, "password": "newpassword1"}).status_code == 200

    listing_after = client.get(f"/api/franchise-owners?franchise_id={franchise.id}", headers=auth_headers)
    row_after = next(r for r in listing_after.json() if r["user_id"] == str(owner.id))
    assert row_after["invited"] is True
    assert row_after["accepted"] is True


def test_invite_requires_franchise_management(client, db):
    """The invite endpoint (reused from Phase 0) is gated server-side; a
    plain instructor with no franchise/studio management role must be
    rejected, same as the owner-assignment routes already are."""
    owner = _make_user(db, "invite-target@test.com", "Invite Target")
    plain_user = _make_user(db, "plain-instructor@test.com", "Plain Instructor")

    login = client.post(
        "/api/auth/login",
        json={"email": "plain-instructor@test.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post("/api/auth/invite", headers=headers, json={"user_id": str(owner.id)})
    assert resp.status_code == 403
