from uuid import UUID

from app.models.franchise import Franchise
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio


def make_franchise(db, name="Relationship Franchise"):
    franchise = Franchise(name=name, is_active=True)
    db.add(franchise)
    db.commit()
    db.refresh(franchise)
    return franchise


def make_studio(db, name="Relationship Studio"):
    studio = Studio(name=name, display_name=name, is_active=True)
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


def test_assign_and_list_studio_in_franchise(client, auth_headers, db):
    franchise = make_franchise(db)
    studio = make_studio(db)

    response = client.post(
        "/api/franchise-studios",
        headers=auth_headers,
        json={"franchise_id": str(franchise.id), "studio_id": str(studio.id), "notes": "Original assignment"},
    )

    assert response.status_code == 201
    assignment = response.json()
    assert assignment["franchise_id"] == str(franchise.id)
    assert assignment["studio_id"] == str(studio.id)

    list_response = client.get(f"/api/franchise-studios?franchise_id={franchise.id}", headers=auth_headers)
    assert list_response.status_code == 200
    assert any(row["id"] == assignment["id"] for row in list_response.json())


def test_studio_cannot_have_two_active_franchises(client, auth_headers, db):
    first_franchise = make_franchise(db, "First Relationship Franchise")
    second_franchise = make_franchise(db, "Second Relationship Franchise")
    studio = make_studio(db, "Exclusive Relationship Studio")

    first = client.post(
        "/api/franchise-studios",
        headers=auth_headers,
        json={"franchise_id": str(first_franchise.id), "studio_id": str(studio.id)},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/franchise-studios",
        headers=auth_headers,
        json={"franchise_id": str(second_franchise.id), "studio_id": str(studio.id)},
    )
    assert second.status_code == 400
    assert "active franchise assignment" in second.json()["detail"]


def test_remove_studio_from_franchise_soft_deactivates_assignment(client, auth_headers, db):
    franchise = make_franchise(db)
    studio = make_studio(db)
    create_response = client.post(
        "/api/franchise-studios",
        headers=auth_headers,
        json={"franchise_id": str(franchise.id), "studio_id": str(studio.id)},
    )
    assignment_id = create_response.json()["id"]

    remove_response = client.delete(f"/api/franchise-studios/{assignment_id}", headers=auth_headers)
    assert remove_response.status_code == 200

    assignment = db.query(FranchiseStudio).filter(FranchiseStudio.id == UUID(assignment_id)).first()
    assert assignment.is_active is False


def test_franchise_studio_routes_require_admin(client, db):
    franchise = make_franchise(db)
    studio = make_studio(db)

    response = client.post(
        "/api/franchise-studios",
        json={"franchise_id": str(franchise.id), "studio_id": str(studio.id)},
    )

    assert response.status_code == 403
