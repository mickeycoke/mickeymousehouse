from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin
from app.models.franchise import Franchise
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.user import User
from app.schemas.franchise_studio import FranchiseStudioCreate, FranchiseStudioResponse, FranchiseStudioUpdate
from app.utils.ownership_validation import (
    reject_active_franchise_studio_conflict,
    validate_franchise_studio_assignment,
)

router = APIRouter(prefix="/api/franchise-studios", tags=["franchise-studios"])


def get_franchise_studio_or_404(db: Session, assignment_id: UUID) -> FranchiseStudio:
    assignment = db.query(FranchiseStudio).filter(FranchiseStudio.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Franchise studio assignment not found")
    return assignment


@router.get("", response_model=List[FranchiseStudioResponse])
def list_franchise_studios(
    franchise_id: Optional[UUID] = None,
    studio_id: Optional[UUID] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(FranchiseStudio)
    if franchise_id:
        query = query.filter(FranchiseStudio.franchise_id == franchise_id)
    if studio_id:
        query = query.filter(FranchiseStudio.studio_id == studio_id)
    if not include_inactive:
        query = query.filter(FranchiseStudio.is_active == True)
    return query.order_by(FranchiseStudio.assigned_at.desc()).all()


@router.post("", response_model=FranchiseStudioResponse, status_code=status.HTTP_201_CREATED)
def assign_studio_to_franchise(
    payload: FranchiseStudioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    validate_franchise_studio_assignment(db, payload.franchise_id, payload.studio_id)
    reject_active_franchise_studio_conflict(db, payload.franchise_id, payload.studio_id)

    existing = (
        db.query(FranchiseStudio)
        .filter(
            FranchiseStudio.franchise_id == payload.franchise_id,
            FranchiseStudio.studio_id == payload.studio_id,
        )
        .order_by(FranchiseStudio.created_at.desc())
        .first()
    )
    if existing:
        existing.is_active = True
        existing.assigned_by_user_id = current_user.id
        existing.notes = payload.notes
        db.commit()
        db.refresh(existing)
        return existing

    assignment = FranchiseStudio(
        franchise_id=payload.franchise_id,
        studio_id=payload.studio_id,
        assigned_by_user_id=current_user.id,
        notes=payload.notes,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/{assignment_id}", response_model=FranchiseStudioResponse)
def get_franchise_studio(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return get_franchise_studio_or_404(db, assignment_id)


@router.put("/{assignment_id}", response_model=FranchiseStudioResponse)
def update_franchise_studio(
    assignment_id: UUID,
    payload: FranchiseStudioUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    assignment = get_franchise_studio_or_404(db, assignment_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}")
def remove_studio_from_franchise(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    assignment = get_franchise_studio_or_404(db, assignment_id)
    assignment.is_active = False
    db.commit()
    return {"message": "Studio removed from franchise"}
