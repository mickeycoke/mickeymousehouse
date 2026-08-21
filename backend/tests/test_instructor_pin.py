"""Shared-device PIN view/set by admin and studio owner.

The PIN is stored recoverably (users.pin) alongside the login hash (users.pin_hash)
so studio owners/managers can view and hand it out. Access is gated to an admin or
the instructor's own studio owner/manager. Setup rows are flushed (not committed);
the endpoint's own commit persists them, so every id/email is stamped-unique to keep
the shared test DB clean across the run.
"""
from uuid import uuid4

from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password, verify_password

STAMP = uuid4().hex[:8]


def _studio(db, label):
    s = Studio(name=f"{label} {uuid4().hex[:6]}", display_name=f"{label} {STAMP}", is_active=True)
    db.add(s)
    db.flush()
    return s


def _instructor(db, studio, *, pin=None):
    u = User(
        email=f"pin-{uuid4().hex[:10]}@import.placeholder.local",
        name=f"Instr {uuid4().hex[:4]}",
        password_hash=hash_password("unusable"),
        role="instructor",
        studio_id=studio.id,
        is_active=True,
        pin_hash=hash_password(pin) if pin else None,
        pin=pin,
    )
    db.add(u)
    db.flush()
    return u


def _owner_headers(db, client, studio):
    email = f"owner-{uuid4().hex[:8]}@example.com"
    owner = User(email=email, name="Owner", password_hash=hash_password("password123"),
                 role="instructor", studio_id=studio.id, is_active=True)
    db.add(owner)
    db.flush()
    db.add(StudioOwner(user_id=owner.id, studio_id=studio.id, level="owner", is_active=True))
    db.flush()
    token = client.post("/api/auth/login",
                        json={"email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── admin: set / view / clear ──────────────────────────────────────────────

def test_admin_sets_pin_stores_plaintext_and_working_hash(client, db, auth_headers):
    inst = _instructor(db, _studio(db, "Admin PIN"))

    resp = client.put(f"/api/users/{inst.id}/pin", json={"pin": "4321"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["pin"] == "4321"
    assert body["has_pin"] is True

    # viewable back
    got = client.get(f"/api/users/{inst.id}/pin", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["pin"] == "4321"

    # hash is kept in sync so shared-device login still verifies
    db.refresh(inst)
    assert inst.pin == "4321"
    assert verify_password("4321", inst.pin_hash)


def test_admin_clears_pin(client, db, auth_headers):
    inst = _instructor(db, _studio(db, "Clear PIN"), pin="1234")

    resp = client.put(f"/api/users/{inst.id}/pin", json={"pin": None}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["pin"] is None
    assert resp.json()["has_pin"] is False

    db.refresh(inst)
    assert inst.pin is None
    assert inst.pin_hash is None


def test_legacy_hash_only_pin_reports_set_but_hidden(client, db, auth_headers):
    # Imported instructors have pin_hash but no recoverable plaintext.
    inst = _instructor(db, _studio(db, "Legacy"), pin=None)
    inst.pin_hash = hash_password("9999")
    db.flush()

    got = client.get(f"/api/users/{inst.id}/pin", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["pin"] is None
    assert got.json()["has_pin"] is True


def test_invalid_pin_rejected(client, db, auth_headers):
    inst = _instructor(db, _studio(db, "Bad PIN"))
    # NEW pins are numeric: too short, too long, or with letters are
    # rejected. Imported alphanumeric PINs still WORK at login — they just
    # aren't something you can newly set here.
    assert client.put(f"/api/users/{inst.id}/pin", json={"pin": "12"}, headers=auth_headers).status_code == 422
    assert client.put(f"/api/users/{inst.id}/pin", json={"pin": "abcd"}, headers=auth_headers).status_code == 422
    assert client.put(f"/api/users/{inst.id}/pin", json={"pin": "123456789"}, headers=auth_headers).status_code == 422


# ── studio owner scoping ───────────────────────────────────────────────────

def test_studio_owner_views_and_sets_own_instructor(client, db):
    studio = _studio(db, "Owned")
    inst = _instructor(db, studio)
    headers = _owner_headers(db, client, studio)

    assert client.put(f"/api/users/{inst.id}/pin", json={"pin": "2468"}, headers=headers).status_code == 200
    got = client.get(f"/api/users/{inst.id}/pin", headers=headers)
    assert got.status_code == 200
    assert got.json()["pin"] == "2468"


def test_studio_owner_blocked_for_other_studio_instructor(client, db):
    owned = _studio(db, "Mine")
    other = _studio(db, "NotMine")
    other_inst = _instructor(db, other)
    headers = _owner_headers(db, client, owned)

    assert client.get(f"/api/users/{other_inst.id}/pin", headers=headers).status_code == 403
    assert client.put(f"/api/users/{other_inst.id}/pin", json={"pin": "1357"}, headers=headers).status_code == 403


def test_pin_requires_auth(client, db):
    inst = _instructor(db, _studio(db, "NoAuth"))
    assert client.get(f"/api/users/{inst.id}/pin").status_code == 403
    assert client.put(f"/api/users/{inst.id}/pin", json={"pin": "1234"}).status_code == 403
