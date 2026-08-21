from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.schemas.ownership import OwnerCandidateResponse, OwnershipScopeResponse
from app.utils.ownership import get_franchise_owner_franchise_id, get_user_ownership_scope, get_instructor_studio_ids

router = APIRouter(prefix="/api/ownership", tags=["ownership"])


@router.get("/scope", response_model=OwnershipScopeResponse)
def get_current_ownership_scope(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scope = get_user_ownership_scope(db, current_user)
    studio_ids = set(scope.studio_ids)
    studio_ids |= get_instructor_studio_ids(db, current_user)
    if current_user.studio_id:
        studio_ids.add(current_user.studio_id)
    return OwnershipScopeResponse(
        is_admin=scope.is_admin,
        studio_ids=sorted(studio_ids),
        franchise_ids=sorted(scope.franchise_ids),
    )


@router.get("/owner-candidates", response_model=List[OwnerCandidateResponse])
def list_owner_candidates(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Admins and franchise OWNERS (the latter to add reporting users to their
    # own franchise) may search people to assign. Reports-only users cannot.
    if current_user.role != "admin" and not get_franchise_owner_franchise_id(db, current_user):
        raise HTTPException(status_code=403, detail="Admin or franchise owner required")
    query = db.query(User).filter(User.is_active == True)
    if q:
        search = f"%{q}%"
        query = query.filter((User.name.ilike(search)) | (User.email.ilike(search)))
    return query.order_by(User.name, User.email).all()
