from uuid import UUID

from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password


def make_owner_user(db):
    existing = db.query(User).filter(User.email == "studio-owner@test.com").first()
    if existing:
        db.query(StudioOwner).filter(StudioOwner.user_id == existing.id).delete()
        db.delete(existing)
    db.commit()
    user = User(
        email="studio-owner@test.com",
        name="Studio Owner",
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_studio(db):
    studio = Studio(name="Test Studio", display_name="Test Studio", is_active=True)
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


def test_assign_and_list_studio_owner(client, auth_headers, db):
    owner = make_owner_user(db)
    studio = make_studio(db)

    response = client.post(
        "/api/studio-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "studio_id": str(studio.id), "notes": "Primary owner"},
    )

    assert response.status_code == 201
    assignment = response.json()
    assert assignment["user_id"] == str(owner.id)
    assert assignment["studio_id"] == str(studio.id)
    assert assignment["is_active"] is True

    list_response = client.get(f"/api/studio-owners?studio_id={studio.id}", headers=auth_headers)
    assert list_response.status_code == 200
    assert any(row["id"] == assignment["id"] for row in list_response.json())


def test_user_can_own_multiple_studios(client, auth_headers, db):
    """Multi-studio: a user may hold owner/manager hats at more than one studio."""
    owner = make_owner_user(db)
    a = make_studio(db)
    b = Studio(name="Studio B", display_name="Studio B", is_active=True)
    db.add(b); db.commit(); db.refresh(b)

    r1 = client.post("/api/studio-owners", headers=auth_headers,
                     json={"user_id": str(owner.id), "studio_id": str(a.id), "level": "owner"})
    assert r1.status_code == 201
    r2 = client.post("/api/studio-owners", headers=auth_headers,
                     json={"user_id": str(owner.id), "studio_id": str(b.id), "level": "manager"})
    assert r2.status_code == 201, r2.text   # previously 422 "one studio per user"

    rows = client.get(f"/api/studio-owners?user_id={owner.id}", headers=auth_headers).json()
    active = {row["studio_id"]: row["level"] for row in rows if row["is_active"]}
    assert active == {str(a.id): "owner", str(b.id): "manager"}


def test_set_user_roles_reconciles_multiple_studio_hats(client, auth_headers, db):
    """The role editor accepts a SET of studio hats and doesn't collapse to one."""
    owner = make_owner_user(db)
    a = make_studio(db)
    b = Studio(name="Studio B2", display_name="Studio B2", is_active=True)
    db.add(b); db.commit(); db.refresh(b)

    resp = client.put(f"/api/roles/user/{owner.id}", headers=auth_headers, json={
        "is_instructor": True,
        "studio_roles": [{"studio_id": str(a.id), "level": "owner"},
                         {"studio_id": str(b.id), "level": "manager"}],
    })
    assert resp.status_code == 200, resp.text
    db.expire_all()
    active = {r.studio_id: r.level for r in db.query(StudioOwner).filter(
        StudioOwner.user_id == owner.id, StudioOwner.is_active == True).all()}
    assert active == {a.id: "owner", b.id: "manager"}

    # Reconcile down to just A — B is deactivated, not left dangling.
    resp = client.put(f"/api/roles/user/{owner.id}", headers=auth_headers, json={
        "is_instructor": True,
        "studio_roles": [{"studio_id": str(a.id), "level": "owner"}],
    })
    assert resp.status_code == 200, resp.text
    db.expire_all()
    active = {r.studio_id for r in db.query(StudioOwner).filter(
        StudioOwner.user_id == owner.id, StudioOwner.is_active == True).all()}
    assert active == {a.id}


def test_duplicate_active_studio_owner_is_rejected(client, auth_headers, db):
    owner = make_owner_user(db)
    studio = make_studio(db)
    payload = {"user_id": str(owner.id), "studio_id": str(studio.id)}

    first = client.post("/api/studio-owners", headers=auth_headers, json=payload)
    assert first.status_code == 201

    duplicate = client.post("/api/studio-owners", headers=auth_headers, json=payload)
    assert duplicate.status_code == 400
    assert "already an active owner" in duplicate.json()["detail"]


def test_remove_studio_owner_soft_deactivates_assignment(client, auth_headers, db):
    owner = make_owner_user(db)
    studio = make_studio(db)
    create_response = client.post(
        "/api/studio-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "studio_id": str(studio.id)},
    )
    assignment_id = create_response.json()["id"]

    remove_response = client.delete(f"/api/studio-owners/{assignment_id}", headers=auth_headers)
    assert remove_response.status_code == 200

    assignment = db.query(StudioOwner).filter(StudioOwner.id == UUID(assignment_id)).first()
    assert assignment.is_active is False


def test_studio_owner_routes_require_admin(client, db):
    owner = make_owner_user(db)
    studio = make_studio(db)

    login_response = client.post(
        "/api/auth/login",
        json={"email": "studio-owner@test.com", "password": "password123"},
    )
    user_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.post(
        "/api/studio-owners",
        headers=user_headers,
        json={"user_id": str(owner.id), "studio_id": str(studio.id)},
    )

    assert response.status_code == 403
