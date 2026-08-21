"""Studio-less staff backlog console (app/routes/studio_assignment.py)."""
from uuid import uuid4

from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.models.user_studio import UserStudio
from app.utils.password import hash_password
from app.utils.tokens import create_access_token


def _studio(db, name):
    s = Studio(name=f"{name} {uuid4().hex[:6]}", display_name=name, is_active=True,
               short_name=f"c{uuid4().hex[:6]}")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _staff(db, name="Trainer", role="instructor", studio_id=None):
    u = User(email=f"s-{uuid4().hex[:8]}@ex.com", name=name, password_hash=hash_password("x"),
             role=role, is_active=True, studio_id=studio_id)
    db.add(u); db.commit(); db.refresh(u)
    return u


# --------------------------------------------------------------------------
# Backlog listing
# --------------------------------------------------------------------------
def test_backlog_lists_studioless_staff(client, db, auth_headers):
    trainer = _staff(db, "Backlog Trainer")

    r = client.get("/api/admin/studio-assignment/backlog", headers=auth_headers)
    assert r.status_code == 200, r.text
    staff = r.json()["staff"]["items"]
    mine = next(s for s in staff if s["id"] == str(trainer.id))
    assert mine["name"] == trainer.name
    assert mine["role"] == "instructor"


def test_backlog_excludes_staff_who_have_a_studio(client, db, auth_headers):
    home = _studio(db, "Has")
    with_primary = _staff(db, "Has Primary", studio_id=home.id)
    owner = _staff(db, "Owns")
    db.add(StudioOwner(user_id=owner.id, studio_id=home.id, level="owner", is_active=True)); db.commit()
    member = _staff(db, "Member")
    db.add(UserStudio(user_id=member.id, studio_id=home.id, is_active=True)); db.commit()

    ids = {s["id"] for s in client.get(
        "/api/admin/studio-assignment/backlog", headers=auth_headers).json()["staff"]["items"]}
    assert str(with_primary.id) not in ids
    assert str(owner.id) not in ids
    assert str(member.id) not in ids


def test_backlog_requires_admin(client, db):
    u = _staff(db, "Not Admin")
    h = {"Authorization": "Bearer " + create_access_token(str(u.id), u.role)}
    assert client.get("/api/admin/studio-assignment/backlog", headers=h).status_code == 403


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------
def test_assign_staff_sets_primary_and_membership_idempotently(client, db, auth_headers):
    studio = _studio(db, "Target")
    trainer = _staff(db, "Assign Me")

    def do():
        return client.post("/api/admin/studio-assignment/assign", headers=auth_headers,
                           json={"studio_id": str(studio.id), "user_ids": [str(trainer.id)]})

    r = do()
    assert r.status_code == 200 and r.json()["staff_assigned"] == 1
    db.expire_all()
    db.refresh(trainer)
    assert trainer.studio_id == studio.id
    active = db.query(UserStudio).filter(UserStudio.user_id == trainer.id,
                                         UserStudio.studio_id == studio.id,
                                         UserStudio.is_active == True).count()
    assert active == 1
    # Re-run: still exactly one active membership (idempotent, no dupes).
    assert do().status_code == 200
    db.expire_all()
    active = db.query(UserStudio).filter(UserStudio.user_id == trainer.id,
                                         UserStudio.studio_id == studio.id,
                                         UserStudio.is_active == True).count()
    assert active == 1


def test_assign_requires_admin(client, db):
    studio = _studio(db, "NoAuth")
    u = _staff(db, "Peon")
    h = {"Authorization": "Bearer " + create_access_token(str(u.id), u.role)}
    r = client.post("/api/admin/studio-assignment/assign", headers=h,
                    json={"studio_id": str(studio.id), "user_ids": [str(u.id)]})
    assert r.status_code == 403
