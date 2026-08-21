"""Admin login log: read the append-only `login_events` audit stream.

Admin-only and global (every studio). Writes happen in the auth routes via
app.services.login_audit; this module is read-only reporting.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, aliased

from app.dependencies import get_db, require_admin
from app.models.login_event import LoginEvent
from app.models.studio import Studio
from app.models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/login-events")
def list_login_events(
    event_type: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Most-recent-first page of login events, with subject/actor/studio names
    resolved. Optional filters: event_type (password|shared_pin|impersonation)
    and success (true|false)."""
    subject = aliased(User)
    actor = aliased(User)
    q = (
        db.query(LoginEvent, subject, actor, Studio)
        .outerjoin(subject, subject.id == LoginEvent.user_id)
        .outerjoin(actor, actor.id == LoginEvent.actor_user_id)
        .outerjoin(Studio, Studio.id == LoginEvent.studio_id)
    )
    if event_type:
        q = q.filter(LoginEvent.event_type == event_type)
    if success is not None:
        q = q.filter(LoginEvent.success == success)

    total = q.count()
    rows = q.order_by(LoginEvent.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for ev, subj, act, studio in rows:
        items.append({
            "id": str(ev.id),
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "event_type": ev.event_type,
            "success": ev.success,
            "user_name": subj.name if subj else None,
            "user_email": subj.email if subj else ev.email_attempted,
            "actor_name": act.name if act else None,
            "studio_name": (studio.display_name or studio.name) if studio else None,
            "ip_address": ev.ip_address,
            "user_agent": ev.user_agent,
            "detail": ev.detail,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}
