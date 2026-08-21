from app.models.franchise import Franchise
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password


def make_validation_user(db, email="ownership-validation@test.com", is_active=True):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        db.query(StudioOwner).filter(StudioOwner.user_id == existing.id).delete()
        db.delete(existing)
    db.commit()
    user = User(
        email=email,
        name="Ownership Validation",
        password_hash=hash_password("password123"),
        role="instructor",
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_studio_owner_assignment_requires_active_user(client, auth_headers, db):
    inactive_user = make_validation_user(db, is_active=False)
    studio = Studio(name="Validation Studio", is_active=True)
    db.add(studio)
    db.commit()
    db.refresh(studio)

    response = client.post(
        "/api/studio-owners",
        headers=auth_headers,
        json={"user_id": str(inactive_user.id), "studio_id": str(studio.id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active user not found"


def test_studio_owner_assignment_requires_active_studio(client, auth_headers, db):
    user = make_validation_user(db)
    inactive_studio = Studio(name="Inactive Validation Studio", is_active=False)
    db.add(inactive_studio)
    db.commit()
    db.refresh(inactive_studio)

    response = client.post(
        "/api/studio-owners",
        headers=auth_headers,
        json={"user_id": str(user.id), "studio_id": str(inactive_studio.id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active studio not found"


def test_franchise_owner_assignment_requires_active_franchise(client, auth_headers, db):
    user = make_validation_user(db)
    inactive_franchise = Franchise(name="Inactive Validation Franchise", is_active=False)
    db.add(inactive_franchise)
    db.commit()
    db.refresh(inactive_franchise)

    response = client.post(
        "/api/franchise-owners",
        headers=auth_headers,
        json={"user_id": str(user.id), "franchise_id": str(inactive_franchise.id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active franchise not found"


def test_franchise_studio_assignment_rejects_existing_active_studio(client, auth_headers, db):
    first_franchise = Franchise(name="Validation First Franchise", is_active=True)
    second_franchise = Franchise(name="Validation Second Franchise", is_active=True)
    studio = Studio(name="Validation Exclusive Studio", is_active=True)
    db.add(first_franchise)
    db.add(second_franchise)
    db.add(studio)
    db.commit()
    db.refresh(first_franchise)
    db.refresh(second_franchise)
    db.refresh(studio)
    db.add(FranchiseStudio(franchise_id=first_franchise.id, studio_id=studio.id, is_active=True))
    db.commit()

    response = client.post(
        "/api/franchise-studios",
        headers=auth_headers,
        json={"franchise_id": str(second_franchise.id), "studio_id": str(studio.id)},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Studio already has an active franchise assignment"
