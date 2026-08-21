from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password


def make_visibility_user(db, email):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        db.query(StudioOwner).filter(StudioOwner.user_id == existing.id).delete()
        db.query(FranchiseOwner).filter(FranchiseOwner.user_id == existing.id).delete()
        db.delete(existing)
    db.commit()
    user = User(
        email=email,
        name=email.split("@")[0],
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_for(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_visibility_studio(db, name):
    studio = Studio(name=name, display_name=name, is_active=True)
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


def test_admin_can_list_all_active_studios(client, auth_headers, db):
    first = make_visibility_studio(db, "Admin Visible Studio 1")
    second = make_visibility_studio(db, "Admin Visible Studio 2")

    response = client.get("/api/studios", headers=auth_headers)

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(first.id) in ids
    assert str(second.id) in ids


def test_studio_owner_only_sees_owned_studios(client, db):
    user = make_visibility_user(db, "studio-scope@test.com")
    visible_studio = make_visibility_studio(db, "Studio Owner Visible")
    hidden_studio = make_visibility_studio(db, "Studio Owner Hidden")
    db.add(StudioOwner(user_id=user.id, studio_id=visible_studio.id, is_active=True))
    db.commit()

    response = client.get("/api/studios", headers=auth_for(client, user.email))

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(visible_studio.id) in ids
    assert str(hidden_studio.id) not in ids


def test_franchise_role_is_franchise_level_not_studio_level(client, db):
    # A franchise role manages the FRANCHISE, not its
    # studios. A franchise owner (with no studio-level role) must NOT get
    # studio-level access to the franchise's studios — the studio list is empty
    # for them — while still seeing the franchise itself at the franchise level.
    user = make_visibility_user(db, "franchise-scope@test.com")
    franchise = Franchise(name="Visibility Franchise", is_active=True)
    franchise_studio = make_visibility_studio(db, "Franchise Studio")
    db.add(franchise)
    db.commit()
    db.refresh(franchise)
    db.add(FranchiseOwner(user_id=user.id, franchise_id=franchise.id, level="owner", is_active=True))
    db.add(FranchiseStudio(franchise_id=franchise.id, studio_id=franchise_studio.id, is_active=True))
    db.commit()

    headers = auth_for(client, user.email)
    # Studio-level: the franchise's studio is NOT visible to a franchise role.
    studios = client.get("/api/studios", headers=headers)
    assert studios.status_code == 200
    assert str(franchise_studio.id) not in {row["id"] for row in studios.json()}
    # Franchise-level: the franchise itself IS visible.
    franchises = client.get("/api/franchises", headers=headers)
    assert franchises.status_code == 200
    assert str(franchise.id) in {row["id"] for row in franchises.json()}


def test_franchise_only_user_sees_no_clients_not_all(db):
    # Regression: removing the franchise->studio expansion must NOT flip a
    # franchise-only user into the "no studios => all clients" (None) branch.
    # They get an empty set (see nothing), never None.
    from app.utils.ownership import get_client_visibility_studio_ids
    user = make_visibility_user(db, "franchise-noclients@test.com")
    user.studio_id = None
    franchise = Franchise(name="NoClient Franchise", is_active=True)
    studio = make_visibility_studio(db, "NoClient Franchise Studio")
    db.add(franchise)
    db.commit()
    db.refresh(franchise)
    db.add(FranchiseOwner(user_id=user.id, franchise_id=franchise.id, level="owner", is_active=True))
    db.add(FranchiseStudio(franchise_id=franchise.id, studio_id=studio.id, is_active=True))
    db.commit()

    visible = get_client_visibility_studio_ids(db, user)
    assert visible == set()   # NOT None (None would mean "all clients")


def test_franchise_owner_only_lists_own_franchise(client, db):
    # A franchise owner must see ONLY their franchise in GET /api/franchises,
    # not every tenant's franchise (regression: the list was unscoped).
    user = make_visibility_user(db, "franchise-list@test.com")
    mine = Franchise(name="My Visible Franchise", is_active=True)
    theirs = Franchise(name="Someone Elses Franchise", is_active=True)
    db.add_all([mine, theirs]); db.commit(); db.refresh(mine); db.refresh(theirs)
    db.add(FranchiseOwner(user_id=user.id, franchise_id=mine.id, level="owner", is_active=True))
    db.commit()

    response = client.get("/api/franchises", headers=auth_for(client, user.email))
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(mine.id) in ids
    assert str(theirs.id) not in ids

    # ...and cannot fetch the out-of-scope franchise directly.
    blocked = client.get(f"/api/franchises/{theirs.id}", headers=auth_for(client, user.email))
    assert blocked.status_code == 404


def test_admin_lists_all_franchises(client, auth_headers, db):
    a = Franchise(name="Admin Franchise A", is_active=True)
    b = Franchise(name="Admin Franchise B", is_active=True)
    db.add_all([a, b]); db.commit(); db.refresh(a); db.refresh(b)
    response = client.get("/api/franchises", headers=auth_headers)
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(a.id) in ids and str(b.id) in ids


def test_get_out_of_scope_studio_returns_403(client, db):
    user = make_visibility_user(db, "out-of-scope@test.com")
    hidden_studio = make_visibility_studio(db, "Out Of Scope Studio")

    response = client.get(f"/api/studios/{hidden_studio.id}", headers=auth_for(client, user.email))

    assert response.status_code == 403
