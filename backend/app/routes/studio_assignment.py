"""Admin tool: clear the studio-less staff backlog.

Some staff (instructors/managers) can end up with no primary studio, no
ownership row, and no `user_studios` membership — they would not appear on
any studio-scoped screen, and once a caller relies on studio scoping they
would see nothing until assigned. This console lists them and lets an admin
assign a studio in bulk. Assignment is idempotent and additive: a staffer
gets `studio_id` set as their primary (only if they had none) plus an active
`user_studios` membership at the target studio.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.models.user_studio import UserStudio

router = APIRouter(prefix="/api/admin/studio-assignment", tags=["studio-assignment"])

STAFF_ROLES_NEEDING_STUDIO = ("instructor", "manager")


def _studioless_staff_query(db: Session):
    """Active instructors/managers with NO studio anywhere — not a primary,
    not an ownership row, not a membership."""
    owner_subq = db.query(StudioOwner.user_id).filter(StudioOwner.is_active == True)
    member_subq = db.query(UserStudio.user_id).filter(UserStudio.is_active == True)
    return (
        db.query(User)
        .filter(
            User.is_active == True,
            User.role.in_(STAFF_ROLES_NEEDING_STUDIO),
            User.studio_id.is_(None),
            ~User.id.in_(owner_subq),
            ~User.id.in_(member_subq),
        )
    )


@router.get("/backlog")
def backlog(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """The studio-less staff backlog: every studio-less staffer."""
    studios = db.query(Studio).filter(Studio.is_active == True).order_by(Studio.name).all()
    studio_name = {s.id: (s.display_name or s.name) for s in studios}

    staff = _studioless_staff_query(db).order_by(User.name).all()
    staff_items = [
        {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "role": u.role,
        }
        for u in staff
    ]

    return {
        "studios": [{"id": str(s.id), "name": studio_name[s.id]} for s in studios],
        "staff": {"total": len(staff_items), "items": staff_items},
    }


class AssignRequest(BaseModel):
    studio_id: UUID
    user_ids: List[UUID] = []


@router.post("/assign")
def assign(
    payload: AssignRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Assign the given studio-less staff to a studio. Idempotent and
    additive — safe to re-run."""
    studio = db.query(Studio).filter(Studio.id == payload.studio_id, Studio.is_active == True).first()
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")

    staff_assigned = 0
    if payload.user_ids:
        users = db.query(User).filter(
            User.id.in_(payload.user_ids),
            User.is_active == True,
            User.role.in_(STAFF_ROLES_NEEDING_STUDIO),
        ).all()
        for u in users:
            # Primary: only fill it in if they had none (never stomp a real home).
            if u.studio_id is None:
                u.studio_id = studio.id
            # Membership: reactivate or create one active row (partial-unique index
            # permits only one active row per (user, studio)).
            row = (
                db.query(UserStudio)
                .filter(UserStudio.user_id == u.id, UserStudio.studio_id == studio.id)
                .order_by(UserStudio.created_at.desc())
                .first()
            )
            if row:
                if not row.is_active:
                    row.is_active = True
                    row.assigned_by_user_id = admin.id
            else:
                db.add(UserStudio(user_id=u.id, studio_id=studio.id,
                                  assigned_by_user_id=admin.id, is_active=True))
            staff_assigned += 1

    db.commit()
    return {
        "studio_id": str(studio.id),
        "studio_name": studio.display_name or studio.name,
        "staff_assigned": staff_assigned,
    }
