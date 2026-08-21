"""Image attachments on notes and chat messages: upload, ACL, linking."""
from uuid import uuid4

from app.models.attachment import Attachment
from app.models.user import User
from app.utils.password import hash_password

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64  # header only — server doesn't parse pixels


def _make_staff(db):
    user = User(email=f"staff-{uuid4().hex[:8]}@test.com", name="Staff",
                password_hash=hash_password("password123"), role="instructor",
                is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, user):
    r = client.post("/api/auth/login",
                    json={"email": user.email, "password": "password123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload(client, headers, name="shot.png", content=PNG, ctype="image/png"):
    return client.post("/api/attachments", headers=headers,
                       files={"file": (name, content, ctype)})


def test_upload_rejects_non_images_and_empty_files(client, auth_headers):
    r = _upload(client, auth_headers, name="notes.txt", content=b"hi", ctype="text/plain")
    assert r.status_code == 400
    r = _upload(client, auth_headers, content=b"")
    assert r.status_code == 400


def test_unlinked_draft_is_private_to_uploader(client, auth_headers, db):
    up = _upload(client, auth_headers).json()
    other = _make_staff(db)
    other_headers = _login(client, other)
    assert client.get(f"/api/attachments/{up['id']}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/attachments/{up['id']}", headers=other_headers).status_code == 404


def test_note_attachment_visible_to_any_signed_in_user(client, auth_headers, db):
    up = _upload(client, auth_headers).json()
    r = client.post("/api/admin/notes", headers=auth_headers,
                    json={"body": f"note-{uuid4().hex[:6]}", "is_active": True,
                          "attachment_ids": [up["id"]]})
    assert r.status_code == 200
    assert [a["id"] for a in r.json()["attachments"]] == [up["id"]]

    staff_headers = _login(client, _make_staff(db))
    img = client.get(f"/api/attachments/{up['id']}", headers=staff_headers)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content == PNG

    history = client.get("/api/notes/history", headers=staff_headers).json()["items"]
    note = next(n for n in history if n["id"] == r.json()["id"])
    assert [a["id"] for a in note["attachments"]] == [up["id"]]


def test_chat_attachment_private_to_asker_and_admin(client, auth_headers, db):
    asker = _make_staff(db)
    asker_headers = _login(client, asker)
    up = _upload(client, asker_headers).json()

    # A screenshot with no text is a valid question.
    r = client.post("/api/questions", headers=asker_headers,
                    json={"body": "", "attachment_ids": [up["id"]]})
    assert r.status_code == 200
    msg = r.json()["messages"][0]
    assert [a["id"] for a in msg["attachments"]] == [up["id"]]

    assert client.get(f"/api/attachments/{up['id']}", headers=asker_headers).status_code == 200
    assert client.get(f"/api/attachments/{up['id']}", headers=auth_headers).status_code == 200
    stranger_headers = _login(client, _make_staff(db))
    assert client.get(f"/api/attachments/{up['id']}", headers=stranger_headers).status_code == 404


def test_cannot_link_someone_elses_draft(client, auth_headers, db):
    thief = _make_staff(db)
    thief_headers = _login(client, thief)
    up = _upload(client, auth_headers).json()   # admin's draft
    r = client.post("/api/questions", headers=thief_headers,
                    json={"body": "mine now", "attachment_ids": [up["id"]]})
    assert r.status_code == 400


def test_admin_can_strip_note_attachment_draft_delete_is_uploader_only(client, auth_headers, db):
    up = _upload(client, auth_headers).json()
    note = client.post("/api/admin/notes", headers=auth_headers,
                       json={"body": "with pic", "is_active": True,
                             "attachment_ids": [up["id"]]}).json()
    assert client.delete(f"/api/attachments/{up['id']}", headers=auth_headers).status_code == 200
    r = client.get("/api/admin/notes", headers=auth_headers)
    fresh = next(n for n in r.json()["items"] if n["id"] == note["id"])
    assert fresh["attachments"] == []

    staff_headers = _login(client, _make_staff(db))
    draft = _upload(client, staff_headers).json()
    assert client.delete(f"/api/attachments/{draft['id']}", headers=auth_headers).status_code == 403
    assert client.delete(f"/api/attachments/{draft['id']}", headers=staff_headers).status_code == 200
    assert db.query(Attachment).filter(Attachment.id == draft["id"]).first() is None
