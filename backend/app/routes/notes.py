"""Notes to users: admin announcements shown at login, and the admin CRUD.

Audience is every signed-in STAFF user. Client-only portal logins are excluded
— these notes are operational messages to instructors/owners, not gym members.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, get_impersonator_id, require_admin
from app.models.user import User
from app.models.user_note import UserNote, UserNoteDismissal
from app.routes.attachments import attachments_for_notes, link_attachments

router = APIRouter(prefix="/api/notes", tags=["notes"])
admin_router = APIRouter(prefix="/api/admin/notes", tags=["notes"])


class NoteBody(BaseModel):
    body: str
    is_active: bool = True
    attachment_ids: list[UUID] = []


def _is_client_only(db: Session, user: User) -> bool:
    """Kept as an explicit hook, but notes are a GENERAL BROADCAST — every
    signed-in user sees them. It previously excluded role 'client', which was
    also just wrong here: the client-portal role in production is 'member',
    so the check silently did nothing anyway.
    """
    return False


def _serialize(note: UserNote) -> dict:
    return {
        "id": str(note.id),
        "body": note.body,
        "is_active": note.is_active,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.get("/active")
def active_notes(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Active notes this user hasn't dismissed since their last edit.

    A dismissal only silences the note as it stood then, so editing a note
    (bumping updated_at) brings it back for everyone.
    """
    if _is_client_only(db, current_user):
        return {"items": []}

    notes = (db.query(UserNote)
             .filter(UserNote.is_active == True)
             .order_by(UserNote.created_at.desc())
             .all())
    if not notes:
        return {"items": []}

    dismissals = {
        d.note_id: d.dismissed_at
        for d in db.query(UserNoteDismissal).filter(
            UserNoteDismissal.user_id == current_user.id,
            UserNoteDismissal.note_id.in_([n.id for n in notes]),
        ).all()
    }
    visible = [n for n in notes
               if not (dismissals.get(n.id) and dismissals[n.id] >= n.updated_at)]
    amap = attachments_for_notes(db, [n.id for n in visible])
    return {"items": [{**_serialize(n), "attachments": amap.get(n.id, [])}
                      for n in visible]}


@router.get("/history")
def notes_history(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Every active note, newest first, flagged with whether this user has
    disregarded it since its last edit. The Notes tab shows undismissed notes
    up top and the rest as a running history underneath."""
    if _is_client_only(db, current_user):
        return {"items": []}

    notes = (db.query(UserNote)
             .filter(UserNote.is_active == True)
             .order_by(UserNote.created_at.desc())
             .all())
    if not notes:
        return {"items": []}

    dismissals = {
        d.note_id: d.dismissed_at
        for d in db.query(UserNoteDismissal).filter(
            UserNoteDismissal.user_id == current_user.id,
            UserNoteDismissal.note_id.in_([n.id for n in notes]),
        ).all()
    }
    amap = attachments_for_notes(db, [n.id for n in notes])
    return {"items": [
        {**_serialize(n),
         "attachments": amap.get(n.id, []),
         "dismissed": bool(dismissals.get(n.id) and dismissals[n.id] >= n.updated_at)}
        for n in notes
    ]}


@router.post("/{note_id}/dismiss")
def dismiss_note(note_id: UUID, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user),
                 impersonator_id: Optional[str] = Depends(get_impersonator_id)):
    """Record (or refresh) this user's Disregard for a note."""
    note = db.query(UserNote).filter(UserNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    # An impersonating admin may click Disregard to preview the flow, but that
    # must never silence the note for the real user — leave their state alone.
    if impersonator_id:
        return {"dismissed": False, "impersonation": True}

    row = db.query(UserNoteDismissal).filter(
        UserNoteDismissal.note_id == note_id,
        UserNoteDismissal.user_id == current_user.id,
    ).first()
    if row:
        row.dismissed_at = datetime.utcnow()
    else:
        db.add(UserNoteDismissal(note_id=note_id, user_id=current_user.id))
    db.commit()
    return {"dismissed": True}


# ── admin panel ───────────────────────────────────────────────────────────
@admin_router.get("")
def list_notes(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    notes = db.query(UserNote).order_by(UserNote.created_at.desc()).all()
    amap = attachments_for_notes(db, [n.id for n in notes])
    return {"items": [{**_serialize(n), "attachments": amap.get(n.id, [])}
                      for n in notes]}


@admin_router.post("")
def create_note(payload: NoteBody, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="A note needs some text.")
    # Announcements are authored by the stable "Platform Team" identity,
    # not whichever admin posted them.
    from app.utils.backend_user import get_backend_user
    note = UserNote(body=body, is_active=payload.is_active,
                    created_by_user_id=get_backend_user(db).id)
    db.add(note)
    db.flush()
    link_attachments(db, payload.attachment_ids, admin, note_id=note.id)
    db.commit()
    db.refresh(note)
    amap = attachments_for_notes(db, [note.id])
    return {**_serialize(note), "attachments": amap.get(note.id, [])}


@admin_router.patch("/{note_id}")
def update_note(note_id: UUID, payload: NoteBody, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    """Editing the text bumps updated_at, which re-shows it to everyone who had
    dismissed it. Toggling is_active alone does the same, deliberately.
    Existing attachments stay; attachment_ids appends newly-uploaded ones
    (individual removal goes through DELETE /api/attachments/{id})."""
    note = db.query(UserNote).filter(UserNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="A note needs some text.")
    note.body = body
    note.is_active = payload.is_active
    note.updated_at = datetime.utcnow()
    link_attachments(db, payload.attachment_ids, admin, note_id=note.id)
    db.commit()
    db.refresh(note)
    amap = attachments_for_notes(db, [note.id])
    return {**_serialize(note), "attachments": amap.get(note.id, [])}


@admin_router.delete("/{note_id}")
def delete_note(note_id: UUID, db: Session = Depends(get_db),
                _: User = Depends(require_admin)):
    note = db.query(UserNote).filter(UserNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    db.query(UserNoteDismissal).filter(UserNoteDismissal.note_id == note_id).delete()
    db.delete(note)
    db.commit()
    return {"deleted": True}
