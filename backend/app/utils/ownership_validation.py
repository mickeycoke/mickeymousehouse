from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User


def require_active_user(db: Session, user_id: UUID) -> User:
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="Active user not found")
    return user


def require_active_studio(db: Session, studio_id: UUID) -> Studio:
    studio = db.query(Studio).filter(Studio.id == studio_id, Studio.is_active == True).first()
    if not studio:
        raise HTTPException(status_code=404, detail="Active studio not found")
    return studio


def require_active_franchise(db: Session, franchise_id: UUID) -> Franchise:
    franchise = db.query(Franchise).filter(Franchise.id == franchise_id, Franchise.is_active == True).first()
    if not franchise:
        raise HTTPException(status_code=404, detail="Active franchise not found")
    return franchise


def validate_studio_owner_assignment(db: Session, user_id: UUID, studio_id: UUID) -> None:
    require_active_user(db, user_id)
    require_active_studio(db, studio_id)


def validate_franchise_owner_assignment(db: Session, user_id: UUID, franchise_id: UUID) -> None:
    require_active_user(db, user_id)
    require_active_franchise(db, franchise_id)


def validate_franchise_studio_assignment(db: Session, franchise_id: UUID, studio_id: UUID) -> None:
    require_active_franchise(db, franchise_id)
    require_active_studio(db, studio_id)


def reject_active_studio_owner_duplicate(db: Session, user_id: UUID, studio_id: UUID) -> None:
    exists = (
        db.query(StudioOwner)
        .filter(
            StudioOwner.user_id == user_id,
            StudioOwner.studio_id == studio_id,
            StudioOwner.is_active == True,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="User is already an active owner for this studio")


def reject_active_franchise_owner_duplicate(db: Session, user_id: UUID, franchise_id: UUID) -> None:
    exists = (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == user_id,
            FranchiseOwner.franchise_id == franchise_id,
            FranchiseOwner.is_active == True,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="User is already an active owner for this franchise")


def reject_active_franchise_studio_conflict(db: Session, franchise_id: UUID, studio_id: UUID) -> None:
    active_assignment = (
        db.query(FranchiseStudio)
        .filter(FranchiseStudio.studio_id == studio_id, FranchiseStudio.is_active == True)
        .first()
    )
    if not active_assignment:
        return
    if active_assignment.franchise_id == franchise_id:
        raise HTTPException(status_code=400, detail="Studio is already active in this franchise")
    raise HTTPException(status_code=400, detail="Studio already has an active franchise assignment")
