from uuid import UUID

from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.user import User
from app.utils.password import hash_password


def make_franchise_owner_user(db):
    existing = db.query(User).filter(User.email == "franchise-owner@test.com").first()
    if existing:
        db.query(FranchiseOwner).filter(FranchiseOwner.user_id == existing.id).delete()
        db.delete(existing)
    db.commit()
    user = User(
        email="franchise-owner@test.com",
        name="Franchise Owner",
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_franchise(db):
    franchise = Franchise(name="Test Owner Franchise", is_active=True)
    db.add(franchise)
    db.commit()
    db.refresh(franchise)
    return franchise


def test_assign_and_list_franchise_owner(client, auth_headers, db):
    owner = make_franchise_owner_user(db)
    franchise = make_franchise(db)

    response = client.post(
        "/api/franchise-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "franchise_id": str(franchise.id), "notes": "Primary owner"},
    )

    assert response.status_code == 201
    assignment = response.json()
    assert assignment["user_id"] == str(owner.id)
    assert assignment["franchise_id"] == str(franchise.id)

    list_response = client.get(f"/api/franchise-owners?franchise_id={franchise.id}", headers=auth_headers)
    assert list_response.status_code == 200
    assert any(row["id"] == assignment["id"] for row in list_response.json())


def test_duplicate_active_franchise_owner_is_rejected(client, auth_headers, db):
    owner = make_franchise_owner_user(db)
    franchise = make_franchise(db)
    payload = {"user_id": str(owner.id), "franchise_id": str(franchise.id)}

    first = client.post("/api/franchise-owners", headers=auth_headers, json=payload)
    assert first.status_code == 201

    duplicate = client.post("/api/franchise-owners", headers=auth_headers, json=payload)
    assert duplicate.status_code == 400
    assert "already an active owner" in duplicate.json()["detail"]


def test_remove_franchise_owner_soft_deactivates_assignment(client, auth_headers, db):
    owner = make_franchise_owner_user(db)
    franchise = make_franchise(db)
    create_response = client.post(
        "/api/franchise-owners",
        headers=auth_headers,
        json={"user_id": str(owner.id), "franchise_id": str(franchise.id)},
    )
    assignment_id = create_response.json()["id"]

    remove_response = client.delete(f"/api/franchise-owners/{assignment_id}", headers=auth_headers)
    assert remove_response.status_code == 200

    assignment = db.query(FranchiseOwner).filter(FranchiseOwner.id == UUID(assignment_id)).first()
    assert assignment.is_active is False


def test_franchise_owner_routes_require_admin(client, db):
    owner = make_franchise_owner_user(db)
    franchise = make_franchise(db)

    login_response = client.post(
        "/api/auth/login",
        json={"email": "franchise-owner@test.com", "password": "password123"},
    )
    user_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.post(
        "/api/franchise-owners",
        headers=user_headers,
        json={"user_id": str(owner.id), "franchise_id": str(franchise.id)},
    )

    assert response.status_code == 403
