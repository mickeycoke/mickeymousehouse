"""Phase 3: an instructor with a user_studios membership works at that studio —
wider client visibility, and appears on / can PIN into that studio's kiosk."""
from uuid import uuid4

from app.models.studio import Studio
from app.models.user import User
from app.models.user_studio import UserStudio
from app.utils.password import hash_password
from app.utils.tokens import create_access_token
from app.utils.ownership import get_client_visibility_studio_ids


def _studio(db, name, code=None):
    s = Studio(name=f"{name} {uuid4().hex[:6]}", display_name=name, is_active=True,
               short_name=code or f"c{uuid4().hex[:6]}")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _instructor(db, primary_studio):
    u = User(email=f"i-{uuid4().hex[:8]}@ms.com", name="Multi Instr",
             password_hash=hash_password("x"), role="instructor", is_active=True,
             studio_id=primary_studio.id, pin="4321", pin_hash=hash_password("4321"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_membership_widens_client_visibility(db, admin_user):
    a, b = _studio(db, "Home"), _studio(db, "Second")
    instr = _instructor(db, a)
    db.add(UserStudio(user_id=instr.id, studio_id=b.id, is_active=True)); db.commit()

    visible = get_client_visibility_studio_ids(db, instr)
    assert a.id in visible and b.id in visible   # primary + membership


def test_operating_studio_header_scoped_for_non_admin(client, db, admin_user):
    """A non-admin may focus a studio in their scope via X-Studio-Id, but an
    out-of-scope header is ignored (never a way to reach another studio)."""
    a, foreign = _studio(db, "Mine"), _studio(db, "Foreign")
    instr = _instructor(db, a)  # primary A
    H = {"Authorization": "Bearer " + create_access_token(str(instr.id), instr.role)}

    me = client.get("/api/roles/me", headers={**H, "X-Studio-Id": str(a.id)}).json()
    assert me["active_studio_id"] == str(a.id)              # in-scope: honored
    assert str(a.id) in {s["id"] for s in me["studios"]}

    me2 = client.get("/api/roles/me", headers={**H, "X-Studio-Id": str(foreign.id)}).json()
    assert me2["active_studio_id"] is None                  # out-of-scope: ignored


def test_role_editor_reconciles_instructor_memberships(client, db, admin_user, auth_headers):
    a, b = _studio(db, "RA"), _studio(db, "RB")
    u = User(email=f"r-{uuid4().hex[:8]}@ms.com", name="Recon", password_hash=hash_password("x"),
             role="instructor", is_active=True)
    db.add(u); db.commit(); db.refresh(u)

    r = client.put(f"/api/roles/user/{u.id}", headers=auth_headers, json={
        "is_instructor": True, "home_studio_id": str(a.id),
        "instructor_studio_ids": [str(a.id), str(b.id)]})
    assert r.status_code == 200, r.text
    db.expire_all()
    active = {row.studio_id for row in db.query(UserStudio).filter(
        UserStudio.user_id == u.id, UserStudio.is_active == True).all()}
    assert active == {a.id, b.id}

    # Reconcile down to just A — B deactivated.
    r = client.put(f"/api/roles/user/{u.id}", headers=auth_headers, json={
        "is_instructor": True, "home_studio_id": str(a.id), "instructor_studio_ids": [str(a.id)]})
    assert r.status_code == 200
    db.expire_all()
    active = {row.studio_id for row in db.query(UserStudio).filter(
        UserStudio.user_id == u.id, UserStudio.is_active == True).all()}
    assert active == {a.id}


def test_kiosk_lists_and_logs_in_instructor_at_membership_studio(client, db, admin_user):
    a, b = _studio(db, "HomeK"), _studio(db, "SecondK")
    instr = _instructor(db, a)
    db.add(UserStudio(user_id=instr.id, studio_id=b.id, is_active=True)); db.commit()

    # Kiosk at studio B (a membership, NOT their primary) lists them...
    r = client.post("/api/auth/shared/lookup", json={"studio_code": b.short_name})
    assert r.status_code == 200
    assert str(instr.id) in {i["id"] for i in r.json()["instructors"]}
    # ...and PIN login at B succeeds.
    lg = client.post("/api/auth/shared/login",
                     json={"studio_code": b.short_name, "user_id": str(instr.id), "pin": "4321"})
    assert lg.status_code == 200 and lg.json().get("access_token")
