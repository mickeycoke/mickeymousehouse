"""Questions to staff: a two-way thread between a signed-in user and the admin.

A user opens a thread from the Notes screen; the admin answers from the admin
inbox. Both sides append to the same message list, so it reads as a
conversation rather than a one-shot form.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_admin
from app.models.studio import Studio
from app.models.user import User
from app.models.user_question import UserQuestion, UserQuestionMessage
from app.routes.attachments import attachments_for_messages, link_attachments

router = APIRouter(prefix="/api/questions", tags=["questions"])
admin_router = APIRouter(prefix="/api/admin/questions", tags=["questions"])

VALID_STATUS = {"new", "read", "resolved"}


class QuestionBody(BaseModel):
    body: str = ""
    attachment_ids: list[UUID] = []


class StatusBody(BaseModel):
    status: str


def _messages(db: Session, question_id) -> list:
    rows = (db.query(UserQuestionMessage, User)
            .outerjoin(User, User.id == UserQuestionMessage.author_user_id)
            .filter(UserQuestionMessage.question_id == question_id)
            .order_by(UserQuestionMessage.created_at.asc())
            .all())
    amap = attachments_for_messages(db, [m.id for m, _ in rows])
    return [{
        "id": str(m.id),
        "body": m.body,
        "is_admin_reply": m.is_admin_reply,
        "author_name": author.name if author else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "attachments": amap.get(m.id, []),
    } for m, author in rows]


def _thread(db: Session, q: UserQuestion, asker: User = None, studio: Studio = None) -> dict:
    return {
        "id": str(q.id),
        "status": q.status,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "last_message_at": q.last_message_at.isoformat() if q.last_message_at else None,
        "user_name": asker.name if asker else None,
        "user_email": asker.email if asker else None,
        "studio_name": (studio.display_name or studio.name) if studio else None,
        "messages": _messages(db, q.id),
    }


@router.post("")
def ask_question(payload: QuestionBody, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Open a new thread with the admin. A screenshot alone is a fine
    question — text is only required when there's no attachment."""
    body = (payload.body or "").strip()
    if not body and not payload.attachment_ids:
        raise HTTPException(status_code=400, detail="Please type your question first.")
    now = datetime.utcnow()
    q = UserQuestion(user_id=current_user.id, studio_id=current_user.studio_id,
                     status="new", created_at=now, last_message_at=now)
    db.add(q)
    db.flush()
    msg = UserQuestionMessage(question_id=q.id, author_user_id=current_user.id,
                              is_admin_reply=False, body=body, created_at=now)
    db.add(msg)
    db.flush()
    link_attachments(db, payload.attachment_ids, current_user, message_id=msg.id)
    db.commit()
    db.refresh(q)
    return _thread(db, q, asker=current_user)


@router.get("/mine")
def my_questions(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """My own threads, newest activity first — including the admin's replies."""
    rows = (db.query(UserQuestion)
            .filter(UserQuestion.user_id == current_user.id)
            .order_by(UserQuestion.last_message_at.desc())
            .all())
    return {"items": [_thread(db, q, asker=current_user) for q in rows]}


@router.post("/{question_id}/messages")
def add_message(question_id: UUID, payload: QuestionBody,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """Append to a thread. The asker may reply to their own; admins to any."""
    q = db.query(UserQuestion).filter(UserQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    is_admin = current_user.role == "admin"
    if not is_admin and q.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="That isn't your question.")
    body = (payload.body or "").strip()
    if not body and not payload.attachment_ids:
        raise HTTPException(status_code=400, detail="Please type a message first.")

    now = datetime.utcnow()
    # Admin ("Platform Team") replies are authored by the stable Platform Team
    # identity, not the individual admin; the asker's own messages stay
    # authored by them.
    if is_admin:
        from app.utils.backend_user import get_backend_user
        author_id = get_backend_user(db).id
    else:
        author_id = current_user.id
    msg = UserQuestionMessage(question_id=q.id, author_user_id=author_id,
                              is_admin_reply=is_admin, body=body, created_at=now)
    db.add(msg)
    db.flush()
    # Linking checks the actual uploader (the signed-in admin), not the
    # backend identity the reply is displayed as.
    link_attachments(db, payload.attachment_ids, current_user, message_id=msg.id)
    q.last_message_at = now
    # An admin answering marks it read; the asker writing again re-opens it.
    if is_admin and q.status == "new":
        q.status = "read"
    elif not is_admin and q.status == "resolved":
        q.status = "new"
    db.commit()
    db.refresh(q)
    asker = db.query(User).filter(User.id == q.user_id).first()
    return _thread(db, q, asker=asker)


# ── admin inbox ───────────────────────────────────────────────────────────
@admin_router.get("")
def list_questions(status: Optional[str] = None, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    """Every thread, newest activity first, with sender email + studio."""
    query = (db.query(UserQuestion, User, Studio)
             .outerjoin(User, User.id == UserQuestion.user_id)
             .outerjoin(Studio, Studio.id == UserQuestion.studio_id))
    if status:
        query = query.filter(UserQuestion.status == status)
    rows = query.order_by(UserQuestion.last_message_at.desc()).all()
    return {"items": [_thread(db, q, asker=asker, studio=studio)
                      for q, asker, studio in rows]}


@admin_router.patch("/{question_id}")
def set_status(question_id: UUID, payload: StatusBody, db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    q = db.query(UserQuestion).filter(UserQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    if payload.status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUS)}")
    q.status = payload.status
    db.commit()
    asker = db.query(User).filter(User.id == q.user_id).first()
    studio = db.query(Studio).filter(Studio.id == q.studio_id).first() if q.studio_id else None
    return _thread(db, q, asker=asker, studio=studio)
