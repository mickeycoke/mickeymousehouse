"""Franchise reporting tiers.

Three franchise levels: OWNER (sees the franchise report + may add/invite
reporting users in their own franchise), REPORTS (sees the report only — the
most restricted; cannot manage anyone), and MANAGER (operations, out of scope
here). Owners are further limited to assigning the reports level. Setup rows
are flushed; endpoint commits persist them, so every email is stamped-unique
to keep the shared test DB clean.
"""
from uuid import uuid4

from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.user import User
from app.utils.password import hash_password


def _franchise(db, label):
    f = Franchise(name=f"{label} {uuid4().hex[:6]}", is_active=True)
    db.add(f)
    db.flush()
    return f


def _login(client, email, password="password123"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _franchise_person(db, client, franchise, level):
    email = f"{level}-{uuid4().hex[:8]}@example.com"
    u = User(email=email, name=f"{level} person", password_hash=hash_password("password123"),
             role="member", is_active=True)
    db.add(u)
    db.flush()
    db.add(FranchiseOwner(user_id=u.id, franchise_id=franchise.id, level=level, is_active=True))
    db.flush()
    return u, _login(client, email)


# ── /roles/me flags ────────────────────────────────────────────────────────

def test_me_owner_can_invite(client, db):
    _, headers = _franchise_person(db, client, _franchise(db, "Own"), "owner")
    me = client.get("/api/roles/me", headers=headers).json()
    assert me["franchise_reporting_only"] is True
    assert me["franchise_can_invite"] is True


def test_me_reports_only_cannot_invite(client, db):
    _, headers = _franchise_person(db, client, _franchise(db, "Rep"), "reports")
    me = client.get("/api/roles/me", headers=headers).json()
    assert me["franchise_reporting_only"] is True
    assert me["franchise_can_invite"] is False


def test_me_manager_is_not_reporting_only(client, db):
    _, headers = _franchise_person(db, client, _franchise(db, "Ops"), "manager")
    me = client.get("/api/roles/me", headers=headers).json()
    assert me["franchise_reporting_only"] is False
    assert me["franchise_can_invite"] is False


def test_me_admin(client, db, auth_headers):
    me = client.get("/api/roles/me", headers=auth_headers).json()
    assert me["franchise_reporting_only"] is False


# ── owner happy path: add + invite reporting users ─────────────────────────

def test_owner_adds_assigns_invites(client, db):
    f = _franchise(db, "AddO")
    _, headers = _franchise_person(db, client, f, "owner")

    assert client.get("/api/ownership/owner-candidates", headers=headers).status_code == 200

    new_email = f"rep-{uuid4().hex[:8]}@example.com"
    created = client.post("/api/users", headers=headers,
                          json={"name": "Rep User", "email": new_email, "role": "member"})
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]
    assert created.json()["studio_id"] is None

    assigned = client.post("/api/franchise-owners", headers=headers,
                           json={"user_id": new_id, "franchise_id": str(f.id), "level": "reports"})
    assert assigned.status_code == 201, assigned.text

    listed = client.get(f"/api/franchise-owners?franchise_id={f.id}", headers=headers)
    assert listed.status_code == 200
    assert any(r["user_id"] == new_id for r in listed.json())

    invited = client.post("/api/auth/invite", headers=headers, json={"user_id": new_id})
    assert invited.status_code == 200, invited.text
    assert invited.json()["sent"] is True


# ── reports-only is view-only: every management action is denied ────────────

def test_reports_only_cannot_manage(client, db):
    f = _franchise(db, "RepDeny")
    _, headers = _franchise_person(db, client, f, "reports")
    victim = User(email=f"v-{uuid4().hex[:8]}@example.com", name="V",
                  password_hash=hash_password("x"), role="member", is_active=True)
    db.add(victim); db.flush()

    assert client.get("/api/ownership/owner-candidates", headers=headers).status_code == 403
    assert client.post("/api/users", headers=headers,
                       json={"name": "x", "email": f"x-{uuid4().hex[:8]}@example.com", "role": "member"}).status_code == 403
    assert client.post("/api/franchise-owners", headers=headers,
                       json={"user_id": str(victim.id), "franchise_id": str(f.id), "level": "reports"}).status_code == 403
    assert client.get(f"/api/franchise-owners?franchise_id={f.id}", headers=headers).status_code == 403


# ── owner boundaries ───────────────────────────────────────────────────────

def test_owner_cannot_add_to_other_franchise(client, db):
    _, headers = _franchise_person(db, client, _franchise(db, "Mine"), "owner")
    other = _franchise(db, "NotMine")
    victim = User(email=f"v-{uuid4().hex[:8]}@example.com", name="V",
                  password_hash=hash_password("x"), role="member", is_active=True)
    db.add(victim); db.flush()
    resp = client.post("/api/franchise-owners", headers=headers,
                       json={"user_id": str(victim.id), "franchise_id": str(other.id), "level": "reports"})
    assert resp.status_code == 403


def test_owner_cannot_add_non_reports_level(client, db):
    f = _franchise(db, "OnlyReports")
    _, headers = _franchise_person(db, client, f, "owner")
    victim = User(email=f"v-{uuid4().hex[:8]}@example.com", name="V",
                  password_hash=hash_password("x"), role="member", is_active=True)
    db.add(victim); db.flush()
    for lvl in ("manager", "owner"):
        resp = client.post("/api/franchise-owners", headers=headers,
                           json={"user_id": str(victim.id), "franchise_id": str(f.id), "level": lvl})
        assert resp.status_code == 403, f"level={lvl}"


def test_owner_cannot_create_instructor(client, db):
    _, headers = _franchise_person(db, client, _franchise(db, "NoInstr"), "owner")
    resp = client.post("/api/users", headers=headers,
                       json={"name": "I", "email": f"i-{uuid4().hex[:8]}@example.com", "role": "instructor"})
    assert resp.status_code == 403


def test_owner_list_forced_to_own_franchise(client, db):
    mine = _franchise(db, "MineList")
    _, headers = _franchise_person(db, client, mine, "owner")
    other = _franchise(db, "OtherList")
    other_user = User(email=f"o-{uuid4().hex[:8]}@example.com", name="O",
                      password_hash=hash_password("x"), role="member", is_active=True)
    db.add(other_user); db.flush()
    db.add(FranchiseOwner(user_id=other_user.id, franchise_id=other.id, level="reports", is_active=True)); db.flush()
    listed = client.get(f"/api/franchise-owners?franchise_id={other.id}", headers=headers)
    assert listed.status_code == 200
    assert all(r["user_id"] != str(other_user.id) for r in listed.json())


def test_plain_member_denied(client, db):
    email = f"plain-{uuid4().hex[:8]}@example.com"
    u = User(email=email, name="Plain", password_hash=hash_password("password123"), role="member", is_active=True)
    db.add(u); db.flush()
    headers = _login(client, email)
    assert client.get("/api/ownership/owner-candidates", headers=headers).status_code == 403
