from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_admin
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.user import User
from app.schemas.franchise_owner import FranchiseOwnerCreate, FranchiseOwnerResponse, FranchiseOwnerUpdate
from app.utils.ownership import get_franchise_owner_franchise_id
from app.utils.ownership_validation import (
    reject_active_franchise_owner_duplicate,
    validate_franchise_owner_assignment,
)

router = APIRouter(prefix="/api/franchise-owners", tags=["franchise-owners"])


def _may_manage_franchise_reporting(db: Session, actor: User, franchise_id) -> bool:
    """Admin, or a franchise OWNER (level 'owner') acting on their OWN franchise.
    Reports-only users cannot manage anyone. Owners are further limited to the
    'reports' level by the callers."""
    if actor.role == "admin":
        return True
    return get_franchise_owner_franchise_id(db, actor) == franchise_id



def _with_user_labels(rows, db):
    """Attach user_name/user_email plus invite status so the UI shows people,
    not ids, and knows whether to offer "send setup email" (Phase 3). One
    batched user lookup for the whole list — no per-row queries."""
    users = {u.id: u for u in db.query(User).filter(User.id.in_([r.user_id for r in rows] or [None])).all()}
    out = []
    for r in rows:
        u = users.get(r.user_id)
        d = FranchiseOwnerResponse.model_validate(r).model_dump()
        d["user_name"] = u.name if u else None
        d["user_email"] = u.email if u else None
        d["invited"] = bool(u and u.invite_sent_at)
        d["accepted"] = bool(u and u.password_set_at)
        out.append(d)
    return out

def get_franchise_owner_or_404(db: Session, assignment_id: UUID) -> FranchiseOwner:
    assignment = db.query(FranchiseOwner).filter(FranchiseOwner.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Franchise owner assignment not found")
    return assignment


@router.get("", response_model=List[FranchiseOwnerResponse])
def list_franchise_owners(
    franchise_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Non-admins may only list their OWN franchise's owners.
    if current_user.role != "admin":
        owned = get_franchise_owner_franchise_id(db, current_user)
        if not owned:
            raise HTTPException(status_code=403, detail="Admin or franchise owner required")
        franchise_id = owned  # force scope, ignore any other franchise_id
    query = db.query(FranchiseOwner)
    if franchise_id:
        query = query.filter(FranchiseOwner.franchise_id == franchise_id)
    if user_id:
        query = query.filter(FranchiseOwner.user_id == user_id)
    if not include_inactive:
        query = query.filter(FranchiseOwner.is_active == True)
    return _with_user_labels(query.order_by(FranchiseOwner.assigned_at.desc()).all(), db)


@router.post("", response_model=FranchiseOwnerResponse, status_code=status.HTTP_201_CREATED)
def assign_franchise_owner(
    payload: FranchiseOwnerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Admin (any level) or a franchise owner adding a REPORTS-level user to their
    # own franchise.
    if not _may_manage_franchise_reporting(db, current_user, payload.franchise_id):
        raise HTTPException(status_code=403, detail="You do not manage this franchise")
    if current_user.role != "admin" and payload.level != "reports":
        raise HTTPException(status_code=403, detail="Franchise owners may only add reporting-level users")

    # One franchise per user: block if this user already has an
    # active role on a DIFFERENT franchise.
    other = (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == payload.user_id,
            FranchiseOwner.is_active == True,
            FranchiseOwner.franchise_id != payload.franchise_id,
        )
        .first()
    )
    if other:
        raise HTTPException(
            status_code=422,
            detail="This user already belongs to another franchise. Use a separate account.",
        )

    validate_franchise_owner_assignment(db, payload.user_id, payload.franchise_id)
    reject_active_franchise_owner_duplicate(db, payload.user_id, payload.franchise_id)

    existing = (
        db.query(FranchiseOwner)
        .filter(FranchiseOwner.user_id == payload.user_id, FranchiseOwner.franchise_id == payload.franchise_id)
        .order_by(FranchiseOwner.created_at.desc())
        .first()
    )
    # A franchise owner must never reactivate a manager-level row (would grant ops).
    if existing and current_user.role != "admin" and existing.level != "reports":
        raise HTTPException(status_code=403, detail="Franchise owners may only manage reporting-level users")
    if existing:
        existing.is_active = True
        existing.assigned_by_user_id = current_user.id
        existing.notes = payload.notes
        db.commit()
        db.refresh(existing)
        return existing

    if payload.level not in ("owner", "manager", "reports"):
        raise HTTPException(status_code=422, detail="level must be owner, manager, or reports")
    assignment = FranchiseOwner(
        user_id=payload.user_id,
        franchise_id=payload.franchise_id,
        assigned_by_user_id=current_user.id,
        notes=payload.notes,
        level=payload.level,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/{assignment_id}", response_model=FranchiseOwnerResponse)
def get_franchise_owner(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return get_franchise_owner_or_404(db, assignment_id)


@router.put("/{assignment_id}", response_model=FranchiseOwnerResponse)
def update_franchise_owner(
    assignment_id: UUID,
    payload: FranchiseOwnerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    assignment = get_franchise_owner_or_404(db, assignment_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}")
def remove_franchise_owner(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = get_franchise_owner_or_404(db, assignment_id)
    if not _may_manage_franchise_reporting(db, current_user, assignment.franchise_id):
        raise HTTPException(status_code=403, detail="You do not manage this franchise")
    if current_user.role != "admin" and assignment.level != "reports":
        raise HTTPException(status_code=403, detail="Franchise owners may only remove reporting-level users")
    assignment.is_active = False
    db.commit()
    return {"message": "Franchise owner assignment removed"}
