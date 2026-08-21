from uuid import UUID

from app.models.franchise import Franchise


def cleanup_franchise_name(db, name):
    db.query(Franchise).filter(Franchise.name == name).delete()
    db.commit()


def test_create_and_list_franchise(client, auth_headers, db):
    cleanup_franchise_name(db, "Test Franchise")

    response = client.post(
        "/api/franchises",
        headers=auth_headers,
        json={"name": "Test Franchise", "description": "Phase 3 test", "display_order": 10},
    )

    assert response.status_code == 201
    franchise = response.json()
    assert franchise["name"] == "Test Franchise"
    assert franchise["is_active"] is True

    list_response = client.get("/api/franchises", headers=auth_headers)
    assert list_response.status_code == 200
    assert any(row["id"] == franchise["id"] for row in list_response.json())


def test_update_franchise(client, auth_headers, db):
    cleanup_franchise_name(db, "Editable Franchise")
    franchise = Franchise(name="Editable Franchise", is_active=True)
    db.add(franchise)
    db.commit()
    db.refresh(franchise)

    response = client.put(
        f"/api/franchises/{franchise.id}",
        headers=auth_headers,
        json={"name": "Updated Franchise", "notes": "Updated in test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Franchise"
    assert data["notes"] == "Updated in test"


def test_deactivate_franchise_hides_from_default_list(client, auth_headers, db):
    cleanup_franchise_name(db, "Deactivate Franchise")
    franchise = Franchise(name="Deactivate Franchise", is_active=True)
    db.add(franchise)
    db.commit()
    db.refresh(franchise)

    response = client.delete(f"/api/franchises/{franchise.id}", headers=auth_headers)
    assert response.status_code == 200

    db.expire(franchise)
    db.refresh(franchise)
    assert franchise.is_active is False

    list_response = client.get("/api/franchises", headers=auth_headers)
    assert all(row["id"] != str(franchise.id) for row in list_response.json())

    inactive_response = client.get("/api/franchises?include_inactive=true", headers=auth_headers)
    assert any(row["id"] == str(franchise.id) for row in inactive_response.json())


def test_get_missing_franchise_returns_404(client, auth_headers):
    response = client.get(f"/api/franchises/{UUID(int=0)}", headers=auth_headers)
    assert response.status_code == 404
