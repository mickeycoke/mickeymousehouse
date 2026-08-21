from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.user import User
from app.utils.password import hash_password


def _franchise(db, name):
    f = Franchise(name=name, is_active=True)
    db.add(f)
    db.flush()
    return f


def test_admin_creates_studio_in_chosen_franchise(client, auth_headers, db, admin_user):
    f = _franchise(db, "Assign FA")

    resp = client.post("/api/studios", headers=auth_headers,
                       json={"name": "New Studio A", "franchise_id": str(f.id)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["franchise_id"] == str(f.id)

    link = db.query(FranchiseStudio).filter(
        FranchiseStudio.studio_id == body["id"], FranchiseStudio.is_active == True).one()
    assert str(link.franchise_id) == str(f.id)


def test_admin_reassigns_studio_franchise(client, auth_headers, db, admin_user):
    f1 = _franchise(db, "Assign F1")
    f2 = _franchise(db, "Assign F2")
    studio_id = client.post("/api/studios", headers=auth_headers,
                            json={"name": "Move Me", "franchise_id": str(f1.id)}).json()["id"]

    resp = client.put(f"/api/studios/{studio_id}", headers=auth_headers,
                      json={"franchise_id": str(f2.id)})
    assert resp.status_code == 200
    assert resp.json()["franchise_id"] == str(f2.id)

    active = db.query(FranchiseStudio).filter(
        FranchiseStudio.studio_id == studio_id, FranchiseStudio.is_active == True).all()
    assert len(active) == 1 and str(active[0].franchise_id) == str(f2.id)
    # the old link is retained but deactivated, not deleted
    assert db.query(FranchiseStudio).filter(
        FranchiseStudio.studio_id == studio_id, FranchiseStudio.franchise_id == f1.id,
        FranchiseStudio.is_active == False).count() == 1


def test_franchise_manager_new_studio_auto_joins_their_franchise(client, db):
    f = _franchise(db, "Manager Franchise")
    mgr = User(email="fa-mgr@test.com", name="Mgr", password_hash=hash_password("pw12345"),
               role="instructor", is_active=True)
    db.add(mgr)
    db.flush()
    db.add(FranchiseOwner(user_id=mgr.id, franchise_id=f.id, level="manager", is_active=True))
    db.flush()

    token = client.post("/api/auth/login",
                        json={"email": "fa-mgr@test.com", "password": "pw12345"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # No franchise_id sent — it must still land in the manager's own franchise
    resp = client.post("/api/studios", headers=headers, json={"name": "Mgr Studio"})
    assert resp.status_code == 201
    assert resp.json()["franchise_id"] == str(f.id)
