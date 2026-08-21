from uuid import uuid4

from app.models.user import User
from app.utils.password import hash_password


def make_non_admin_user(db):
    existing = db.query(User).filter(User.email == "ownership-denied@test.com").first()
    if existing:
        db.delete(existing)
    db.commit()
    user = User(
        email="ownership-denied@test.com",
        name="Ownership Denied",
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def non_admin_headers(client, user):
    response = client.post("/api/auth/login", json={"email": user.email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_ownership_mutation_routes_require_auth(client):
    payload = {"user_id": str(uuid4()), "studio_id": str(uuid4())}

    assert client.post("/api/studio-owners", json=payload).status_code == 403
    assert client.post(
        "/api/franchise-owners",
        json={"user_id": str(uuid4()), "franchise_id": str(uuid4())},
    ).status_code == 403
    assert client.post(
        "/api/franchise-studios",
        json={"franchise_id": str(uuid4()), "studio_id": str(uuid4())},
    ).status_code == 403
    assert client.post("/api/franchises", json={"name": "Denied Franchise"}).status_code == 403


def test_non_admin_cannot_mutate_ownership(client, db):
    user = make_non_admin_user(db)
    headers = non_admin_headers(client, user)

    assert client.post(
        "/api/studio-owners",
        headers=headers,
        json={"user_id": str(uuid4()), "studio_id": str(uuid4())},
    ).status_code == 403
    assert client.post(
        "/api/franchise-owners",
        headers=headers,
        json={"user_id": str(uuid4()), "franchise_id": str(uuid4())},
    ).status_code == 403
    assert client.post(
        "/api/franchise-studios",
        headers=headers,
        json={"franchise_id": str(uuid4()), "studio_id": str(uuid4())},
    ).status_code == 403
    assert client.post(
        "/api/franchises",
        headers=headers,
        json={"name": "Denied Franchise"},
    ).status_code == 403


def test_owner_candidate_lookup_requires_admin(client, db):
    user = make_non_admin_user(db)

    assert client.get("/api/ownership/owner-candidates").status_code == 403
    assert client.get(
        "/api/ownership/owner-candidates",
        headers=non_admin_headers(client, user),
    ).status_code == 403
