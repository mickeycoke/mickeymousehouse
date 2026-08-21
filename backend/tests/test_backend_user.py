"""Team communications are authored by the Platform Team identity."""
from uuid import uuid4

from app.models.user import User
from app.models.user_note import UserNote
from app.models.user_question import UserQuestion, UserQuestionMessage
from app.utils.backend_user import BACKEND_USER_EMAIL, get_backend_user
from app.utils.password import hash_password


def test_get_backend_user_is_idempotent_admin(db):
    a = get_backend_user(db); db.commit()
    b = get_backend_user(db); db.commit()
    assert a.id == b.id                       # one canonical row
    assert a.role == "admin"                  # ordinary admin, no special role
    assert a.email == BACKEND_USER_EMAIL


def test_note_is_authored_by_backend_user(client, auth_headers, db):
    r = client.post("/api/admin/notes", headers=auth_headers,
                    json={"body": "Scheduled maintenance tonight.", "is_active": True})
    assert r.status_code == 200
    note = db.query(UserNote).filter(UserNote.id == r.json()["id"]).first()
    assert note.created_by_user_id == get_backend_user(db).id


def test_admin_reply_authored_by_backend_asker_message_stays_theirs(client, auth_headers, db):
    from datetime import datetime
    # A member asked a question (built directly — members can't use staff login).
    asker = User(email=f"asker-{uuid4().hex[:6]}@t.test", name="Asker",
                 password_hash=hash_password("x"), role="member", is_active=True)
    db.add(asker); db.commit()
    q = UserQuestion(user_id=asker.id, status="new", created_at=datetime.utcnow(),
                     last_message_at=datetime.utcnow())
    db.add(q); db.commit()
    db.add(UserQuestionMessage(question_id=q.id, author_user_id=asker.id,
                               is_admin_reply=False, body="How do I reset a PIN?",
                               created_at=datetime.utcnow()))
    db.commit()

    # admin ("team") replies via the endpoint
    rep = client.post(f"/api/questions/{q.id}/messages", headers=auth_headers,
                      json={"body": "Open the instructor and tap Reset PIN."})
    assert rep.status_code == 200

    backend_id = get_backend_user(db).id
    msgs = (db.query(UserQuestionMessage)
            .filter(UserQuestionMessage.question_id == q.id)
            .order_by(UserQuestionMessage.created_at).all())
    asker_msg = next(m for m in msgs if not m.is_admin_reply)
    admin_msg = next(m for m in msgs if m.is_admin_reply)
    assert asker_msg.author_user_id == asker.id        # asker keeps authorship
    assert admin_msg.author_user_id == backend_id      # team reply = Backend user
