from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_admin
from app.models.franchise import Franchise
from app.models.user import User
from app.schemas.franchise import FranchiseCreate, FranchiseResponse, FranchiseUpdate
from app.utils.ownership import can_view_franchise, get_user_ownership_scope

router = APIRouter(prefix="/api/franchises", tags=["franchises"])


def get_franchise_or_404(db: Session, franchise_id: UUID) -> Franchise:
    franchise = db.query(Franchise).filter(Franchise.id == franchise_id).first()
    if not franchise:
        raise HTTPException(status_code=404, detail="Franchise not found")
    return franchise


@router.get("", response_model=List[FranchiseResponse])
def list_franchises(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Franchise)
    if not include_inactive:
        query = query.filter(Franchise.is_active == True)
    # Scope to what the caller may see: admins get every franchise; everyone
    # else only the franchise(s) they own/manage/belong to. Without this a
    # franchise owner saw ALL franchises (incl. other tenants' data).
    scope = get_user_ownership_scope(db, current_user)
    if not scope.is_admin:
        if not scope.franchise_ids:
            return []
        query = query.filter(Franchise.id.in_(scope.franchise_ids))
    return query.order_by(Franchise.display_order, Franchise.name).all()


@router.post("", response_model=FranchiseResponse, status_code=status.HTTP_201_CREATED)
def create_franchise(
    payload: FranchiseCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    franchise = Franchise(**payload.model_dump())
    db.add(franchise)
    db.commit()
    db.refresh(franchise)
    return franchise


@router.get("/{franchise_id}", response_model=FranchiseResponse)
def get_franchise(
    franchise_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    franchise = get_franchise_or_404(db, franchise_id)
    # Same scoping as the list: don't leak a franchise the caller can't see.
    if not can_view_franchise(db, current_user, franchise_id):
        raise HTTPException(status_code=404, detail="Franchise not found")
    return franchise


@router.put("/{franchise_id}", response_model=FranchiseResponse)
def update_franchise(
    franchise_id: UUID,
    payload: FranchiseUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    franchise = get_franchise_or_404(db, franchise_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(franchise, field, value)
    db.commit()
    db.refresh(franchise)
    return franchise


@router.delete("/{franchise_id}")
def deactivate_franchise(
    franchise_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    franchise = get_franchise_or_404(db, franchise_id)
    franchise.is_active = False
    db.commit()
    return {"message": "Franchise deactivated"}
