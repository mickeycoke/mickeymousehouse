from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import (
    get_db, require_admin, require_franchise_management, get_managed_franchise_id,
    get_operating_studio_id,
)
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.schemas.studio_owner import StudioOwnerCreate, StudioOwnerResponse, StudioOwnerUpdate

from app.utils.ownership import get_managed_studio_ids
from app.utils.ownership_validation import (
    reject_active_studio_owner_duplicate,
    validate_studio_owner_assignment,
)

router = APIRouter(prefix="/api/studio-owners", tags=["studio-owners"])


def _manageable_studio_ids(db: Session, current_user: User, operating_studio_id):
    """Which studios' OWNER ASSIGNMENTS may this caller touch?
    `None` = unrestricted (an admin who has not selected a studio).

    WHY THIS IS NOT A `StudioScopedRepo` IN `app/data/`.
    StudioOwner does carry a `studio_id`, so the model looks studio-scoped — but
    the CALLER on every endpoint in this file is a franchise manager or an admin,
    never studio staff, and the question that must be answered is "does this
    caller MANAGE that studio", not "may this caller see that studio's client
    data". Those are different sets, and here they are near-opposites:
    `AccessScope.visible_studio_ids` (what StudioScopedRepo filters on) comes
    from `get_client_visibility_studio_ids`, which deliberately returns an EMPTY
    set for a franchise-level user with no studio attachment — "franchise roles
    get NO studio client data". A StudioOwnerRepo built on that would 404 a
    franchise manager's own studios' assignments and break owner management
    entirely. Overriding `_apply_scope` to consult `get_managed_studio_ids` plus
    the franchise closure instead would make it a StudioScopedRepo in name only,
    and would put a SECOND copy of the management rule next to the one the POST
    path already uses — the drift CLAUDE.md's history section blames for the
    original leaks. So: one rule, one implementation, consulted by list, POST
    and all three by-id paths.

    Mirrors `routes/studios.py::studio_qr_targets`: `get_managed_studio_ids`
    returns None for a genuinely unrestricted admin and honours
    `operating_studio_id`, so an admin who has selected a studio (or been scoped
    by an impersonation token) is held to it here as everywhere else. A
    franchise manager falls back to the studios in their franchise.
    """
    managed = get_managed_studio_ids(db, current_user, operating_studio_id=operating_studio_id)
    if managed is None:
        return None
    ids = set(managed)
    fid = get_managed_franchise_id(db, current_user)
    if fid and fid != "ALL":
        ids |= {
            row.studio_id
            for row in db.query(FranchiseStudio).filter(
                FranchiseStudio.franchise_id == fid,
                FranchiseStudio.is_active == True,  # noqa: E712
            ).all()
        }
    return ids


def _require_caller_manages_studio(
    db: Session, current_user: User, studio_id: UUID, operating_studio_id
) -> None:
    """Refuse an owner assignment aimed at a studio the caller cannot manage.

    Used by POST, where the caller NAMED the studio: 403 is right there, because
    the studio id came from the caller and its existence is not a secret. The
    by-id paths answer 404 instead — see `get_studio_owner_or_404`.
    """
    if not db.query(Studio.id).filter(Studio.id == studio_id).first():
        raise HTTPException(status_code=404, detail="Studio not found")
    manageable = _manageable_studio_ids(db, current_user, operating_studio_id)
    if manageable is None or studio_id in manageable:
        return
    raise HTTPException(status_code=403, detail="You do not manage this studio")



def _with_user_labels(rows, db):
    """Attach user_name/user_email plus invite status so the UI shows people,
    not ids, and knows whether to offer "send setup email" (Phase 2). One
    batched user lookup for the whole list — no per-row queries."""
    users = {u.id: u for u in db.query(User).filter(User.id.in_([r.user_id for r in rows] or [None])).all()}
    out = []
    for r in rows:
        u = users.get(r.user_id)
        d = StudioOwnerResponse.model_validate(r).model_dump()
        d["user_name"] = u.name if u else None
        d["user_email"] = u.email if u else None
        d["invited"] = bool(u and u.invite_sent_at)
        d["accepted"] = bool(u and u.password_set_at)
        out.append(d)
    return out

_NOT_FOUND = "Studio owner assignment not found"


def get_studio_owner_or_404(
    db: Session, assignment_id: UUID, current_user: User, operating_studio_id
) -> StudioOwner:
    """Fetch by primary key AND authorize the caller against the studio the
    assignment points at.

    This was a bare primary-key fetch. `require_franchise_management` admits
    every franchise MANAGER, so any of them could read, rewrite or deactivate an
    owner assignment belonging to another franchise's studio — a
    denial-of-access hole (`is_active=false` locks a legitimate studio owner out
    of their own studio) as well as a disclosure. The POST path grew
    `_require_caller_manages_studio` when the escalation hole was found there;
    these three paths were missed.

    `current_user`/`operating_studio_id` are REQUIRED positionals on purpose: an
    optional authorization argument is an optional check, and CLAUDE.md's
    history is what happens when a correct helper is optional to call.

    404, not 403, and the SAME detail string as a genuinely missing row:
    whether an assignment exists in another franchise is not this caller's
    business (CLAUDE.md — "by id is not exempt").
    """
    assignment = db.query(StudioOwner).filter(StudioOwner.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    manageable = _manageable_studio_ids(db, current_user, operating_studio_id)
    if manageable is not None and assignment.studio_id not in manageable:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return assignment


@router.get("", response_model=List[StudioOwnerResponse])
def list_studio_owners(
    studio_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    # Same hole as the by-id paths, and the one that actually disclosed PII:
    # `_with_user_labels` attaches user_name/user_email, so an unfiltered list
    # handed every franchise manager the name and email of every other
    # franchise's studio owners. Scope to the studios this caller manages.
    manageable = _manageable_studio_ids(db, current_user, operating_studio_id)
    if manageable is not None and not manageable:
        return []
    query = db.query(StudioOwner)
    if manageable is not None:
        query = query.filter(StudioOwner.studio_id.in_(manageable))
    if studio_id:
        query = query.filter(StudioOwner.studio_id == studio_id)
    if user_id:
        query = query.filter(StudioOwner.user_id == user_id)
    if not include_inactive:
        query = query.filter(StudioOwner.is_active == True)
    return _with_user_labels(query.order_by(StudioOwner.assigned_at.desc()).all(), db)


@router.post("", response_model=StudioOwnerResponse, status_code=status.HTTP_201_CREATED)
def assign_studio_owner(
    payload: StudioOwnerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    # PRIVILEGE ESCALATION GUARD. This validated the user/studio pair but never
    # checked the CALLER may manage the target studio, so a franchise manager
    # could post an assignment for any studio in the system — including making
    # themselves its owner — after which every downstream scope check passes
    # legitimately, because the assignment is real. `studios.py::update_studio`
    # already carries this exact check; studio_owners was missing it.
    _require_caller_manages_studio(db, current_user, payload.studio_id, operating_studio_id)

    # A user may hold owner/manager hats at MULTIPLE studios (multi-studio staff).
    # Only a duplicate at the SAME studio is rejected (reject_active_..._duplicate).
    validate_studio_owner_assignment(db, payload.user_id, payload.studio_id)
    reject_active_studio_owner_duplicate(db, payload.user_id, payload.studio_id)

    existing = (
        db.query(StudioOwner)
        .filter(StudioOwner.user_id == payload.user_id, StudioOwner.studio_id == payload.studio_id)
        .order_by(StudioOwner.created_at.desc())
        .first()
    )
    if existing:
        existing.is_active = True
        existing.assigned_by_user_id = current_user.id
        existing.notes = payload.notes
        # Re-adding a person must honor the level the caller just chose — a
        # reactivated row silently keeping its OLD level is how "I picked owner
        # and got manager" can happen: the person already had an inactive
        # manager row, so reactivation ignored the new owner choice.
        existing.level = payload.level
        db.commit()
        db.refresh(existing)
        return existing

    assignment = StudioOwner(
        user_id=payload.user_id,
        studio_id=payload.studio_id,
        assigned_by_user_id=current_user.id,
        notes=payload.notes,
        level=payload.level,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/{assignment_id}", response_model=StudioOwnerResponse)
def get_studio_owner(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    return get_studio_owner_or_404(db, assignment_id, current_user, operating_studio_id)


@router.put("/{assignment_id}", response_model=StudioOwnerResponse)
def update_studio_owner(
    assignment_id: UUID,
    payload: StudioOwnerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    assignment = get_studio_owner_or_404(db, assignment_id, current_user, operating_studio_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}")
def remove_studio_owner(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    assignment = get_studio_owner_or_404(db, assignment_id, current_user, operating_studio_id)
    assignment.is_active = False
    db.commit()
    return {"message": "Studio owner assignment removed"}
