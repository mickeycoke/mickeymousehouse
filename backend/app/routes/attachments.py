"""Image attachments: screenshots and pasted QR codes on notes and chat.

Upload-first flow: a composer uploads each picture as it is added (paste or
file picker), then passes the returned ids when the note/message is created,
which links them. Unlinked uploads are private drafts — only their uploader
can see them, and stale ones are swept opportunistically.
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session, undefer

from app.dependencies import get_db, get_current_user
from app.models.attachment import Attachment
from app.models.user import User
from app.models.user_question import UserQuestion, UserQuestionMessage

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Markdown, so a release note can be attached as a file rather than pasted.
# Browsers are inconsistent about `.md`: Chrome usually sends text/markdown,
# Safari often text/plain, and some send an empty content type — so the
# EXTENSION is what decides, with the declared type only used to reject
# something obviously else. Served back with a text/markdown media type and,
# critically, never rendered as HTML (see `download_attachment`).
ALLOWED_TEXT_TYPES = {"text/markdown", "text/x-markdown", "text/plain", ""}
MARKDOWN_EXTS = (".md", ".markdown")
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_TEXT_TYPES
MAX_BYTES = 10 * 1024 * 1024  # 10 MB — plenty for a screenshot
DRAFT_TTL = timedelta(hours=24)


def serialize_attachment(a: Attachment) -> dict:
    return {
        "id": str(a.id),
        "filename": a.filename,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
    }


def attachments_for_notes(db: Session, note_ids: list) -> dict:
    """{note_id: [serialized]} for a batch of notes, blobs untouched."""
    if not note_ids:
        return {}
    out: dict = {}
    rows = (db.query(Attachment).filter(Attachment.note_id.in_(note_ids))
            .order_by(Attachment.created_at.asc()).all())
    for a in rows:
        out.setdefault(a.note_id, []).append(serialize_attachment(a))
    return out


def attachments_for_messages(db: Session, message_ids: list) -> dict:
    """{message_id: [serialized]} for a batch of messages, blobs untouched."""
    if not message_ids:
        return {}
    out: dict = {}
    rows = (db.query(Attachment)
            .filter(Attachment.question_message_id.in_(message_ids))
            .order_by(Attachment.created_at.asc()).all())
    for a in rows:
        out.setdefault(a.question_message_id, []).append(serialize_attachment(a))
    return out


def link_attachments(db: Session, ids: list, user: User, *,
                     note_id=None, message_id=None) -> None:
    """Attach previously-uploaded drafts to their parent. Each id must exist,
    be unlinked, and have been uploaded by the caller — anything else is a 400
    so a bad id never silently drops a picture."""
    for raw in ids or []:
        a = db.query(Attachment).filter(Attachment.id == raw).first()
        if (not a or a.note_id or a.question_message_id
                or a.uploaded_by_user_id != user.id):
            raise HTTPException(status_code=400, detail="Unknown attachment.")
        a.note_id = note_id
        a.question_message_id = message_id


@router.post("")
async def upload_attachment(file: UploadFile, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    declared = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    is_markdown = name.endswith(MARKDOWN_EXTS) and declared in ALLOWED_TEXT_TYPES
    if not is_markdown and declared not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only PNG, JPEG, WebP or GIF images, or a .md file, can be attached.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Attachments can be at most 10 MB.")

    # Sweep this user's abandoned drafts (pasted but never sent) while we're here.
    db.query(Attachment).filter(
        Attachment.uploaded_by_user_id == current_user.id,
        Attachment.note_id.is_(None), Attachment.question_message_id.is_(None),
        Attachment.created_at < datetime.utcnow() - DRAFT_TTL,
    ).delete()

    a = Attachment(uploaded_by_user_id=current_user.id,
                   filename=file.filename or ("note.md" if is_markdown else "image"),
                   # Normalise: a .md that arrived as text/plain (Safari) or with
                   # no type at all is stored as text/markdown so the download
                   # path does not have to re-guess.
                   content_type="text/markdown" if is_markdown else declared,
                   size_bytes=len(data), data=data)
    db.add(a)
    db.commit()
    db.refresh(a)
    return serialize_attachment(a)


@router.get("/{attachment_id}")
def get_attachment(attachment_id: UUID, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    a = (db.query(Attachment).options(undefer(Attachment.data))
         .filter(Attachment.id == attachment_id).first())
    if not a:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if a.note_id:
        pass  # notes are a general broadcast — any signed-in user may view
    elif a.question_message_id:
        # Chat threads are private: only the asker and admins.
        if current_user.role != "admin":
            q = (db.query(UserQuestion)
                 .join(UserQuestionMessage,
                       UserQuestionMessage.question_id == UserQuestion.id)
                 .filter(UserQuestionMessage.id == a.question_message_id)
                 .first())
            if not q or q.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="Attachment not found")
    elif a.uploaded_by_user_id != current_user.id:
        # Unlinked draft — its uploader only.
        raise HTTPException(status_code=404, detail="Attachment not found")

    # nosniff matters now that non-image types are allowed: without it a
    # browser may sniff a text/* body containing markup and render it as HTML,
    # which would turn an attached .md into a script-execution surface. The
    # markdown renderer in the app never emits raw HTML either — both ends.
    return Response(content=a.data, media_type=a.content_type,
                    headers={"Cache-Control": "private, max-age=3600",
                             "X-Content-Type-Options": "nosniff"})


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: UUID, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Uploaders may discard their own drafts; admins may also strip a picture
    from a note (the edit flow). Chat messages are immutable — no removal."""
    a = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Attachment not found")
    is_draft = not a.note_id and not a.question_message_id
    may_delete = ((is_draft and a.uploaded_by_user_id == current_user.id)
                  or (a.note_id and current_user.role == "admin"))
    if not may_delete:
        raise HTTPException(status_code=403, detail="You can't remove that attachment.")
    db.delete(a)
    db.commit()
    return {"deleted": True}
