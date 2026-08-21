"""Notes to users: the history view and the impersonation dismiss guard."""
from uuid import uuid4

from app.models.user import User
from app.models.user_note import UserNote, UserNoteDismissal
from app.utils.password import hash_password


def _make_staff(db, role="instructor"):
    user = User(email=f"staff-{uuid4().hex[:8]}@test.com", name="Staff",
                password_hash=hash_password("password123"), role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, user):
    r = client.post("/api/auth/login",
                    json={"email": user.email, "password": "password123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _post_note(client, auth_headers, body):
    r = client.post("/api/admin/notes", headers=auth_headers,
                    json={"body": body, "is_active": True})
    assert r.status_code == 200
    return r.json()["id"]


def test_history_keeps_dismissed_notes_active_drops_them(client, auth_headers, db):
    staff = _make_staff(db)
    headers = _login(client, staff)
    kept = _post_note(client, auth_headers, f"kept-{uuid4().hex[:6]}")
    dismissed = _post_note(client, auth_headers, f"dismissed-{uuid4().hex[:6]}")

    r = client.post(f"/api/notes/{dismissed}/dismiss", headers=headers)
    assert r.status_code == 200 and r.json()["dismissed"] is True

    active_ids = {n["id"] for n in client.get("/api/notes/active", headers=headers).json()["items"]}
    assert kept in active_ids and dismissed not in active_ids

    history = {n["id"]: n for n in client.get("/api/notes/history", headers=headers).json()["items"]}
    assert history[kept]["dismissed"] is False
    assert history[dismissed]["dismissed"] is True      # stays visible as history


def test_history_excludes_hidden_notes(client, auth_headers, db):
    staff = _make_staff(db)
    headers = _login(client, staff)
    note_id = _post_note(client, auth_headers, f"soon-hidden-{uuid4().hex[:6]}")

    r = client.patch(f"/api/admin/notes/{note_id}", headers=auth_headers,
                     json={"body": "soon hidden", "is_active": False})
    assert r.status_code == 200

    history_ids = {n["id"] for n in client.get("/api/notes/history", headers=headers).json()["items"]}
    assert note_id not in history_ids


def test_editing_a_note_returns_it_to_new_in_history(client, auth_headers, db):
    staff = _make_staff(db)
    headers = _login(client, staff)
    note_id = _post_note(client, auth_headers, f"editable-{uuid4().hex[:6]}")

    client.post(f"/api/notes/{note_id}/dismiss", headers=headers)
    r = client.patch(f"/api/admin/notes/{note_id}", headers=auth_headers,
                     json={"body": "edited body", "is_active": True})
    assert r.status_code == 200

    history = {n["id"]: n for n in client.get("/api/notes/history", headers=headers).json()["items"]}
    assert history[note_id]["dismissed"] is False       # edit re-surfaces it


def test_impersonated_dismiss_never_touches_the_real_user(client, auth_headers, db):
    staff = _make_staff(db)
    note_id = _post_note(client, auth_headers, f"broadcast-{uuid4().hex[:6]}")

    r = client.post(f"/api/auth/impersonate/{staff.id}", headers=auth_headers)
    assert r.status_code == 200
    imp_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post(f"/api/notes/{note_id}/dismiss", headers=imp_headers)
    assert r.status_code == 200
    assert r.json() == {"dismissed": False, "impersonation": True}

    # No dismissal row was written, and the real user still sees the note.
    assert db.query(UserNoteDismissal).filter(
        UserNoteDismissal.note_id == note_id,
        UserNoteDismissal.user_id == staff.id,
    ).first() is None
    headers = _login(client, staff)
    active_ids = {n["id"] for n in client.get("/api/notes/active", headers=headers).json()["items"]}
    assert note_id in active_ids


def test_real_login_dismiss_still_works(client, auth_headers, db):
    staff = _make_staff(db)
    headers = _login(client, staff)
    note_id = _post_note(client, auth_headers, f"dismissable-{uuid4().hex[:6]}")

    r = client.post(f"/api/notes/{note_id}/dismiss", headers=headers)
    assert r.status_code == 200 and r.json()["dismissed"] is True
    assert db.query(UserNoteDismissal).filter(
        UserNoteDismissal.note_id == note_id,
        UserNoteDismissal.user_id == staff.id,
    ).first() is not None


def test_admin_delete_removes_note_from_every_users_history(
    client, auth_headers, db
):
    first_staff = _make_staff(db)
    second_staff = _make_staff(db)
    first_headers = _login(client, first_staff)
    second_headers = _login(client, second_staff)
    note_id = _post_note(client, auth_headers, f"delete-everywhere-{uuid4().hex[:6]}")

    # Both users receive independent history/dismissal state.
    assert note_id in {
        n["id"]
        for n in client.get("/api/notes/history", headers=first_headers).json()["items"]
    }
    assert note_id in {
        n["id"]
        for n in client.get("/api/notes/history", headers=second_headers).json()["items"]
    }
    assert client.post(
        f"/api/notes/{note_id}/dismiss", headers=first_headers
    ).status_code == 200
    assert client.post(
        f"/api/notes/{note_id}/dismiss", headers=second_headers
    ).status_code == 200

    # Admin deletion is global: admin inventory, every user's history, and
    # per-user dismissal rows all lose the note.
    response = client.delete(f"/api/admin/notes/{note_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    admin_ids = {
        n["id"]
        for n in client.get("/api/admin/notes", headers=auth_headers).json()["items"]
    }
    first_history_ids = {
        n["id"]
        for n in client.get("/api/notes/history", headers=first_headers).json()["items"]
    }
    second_history_ids = {
        n["id"]
        for n in client.get("/api/notes/history", headers=second_headers).json()["items"]
    }
    assert note_id not in admin_ids
    assert note_id not in first_history_ids
    assert note_id not in second_history_ids
    assert db.query(UserNote).filter(UserNote.id == note_id).first() is None
    assert db.query(UserNoteDismissal).filter(
        UserNoteDismissal.note_id == note_id
    ).count() == 0
