from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FranchiseOwnerCreate(BaseModel):
    user_id: UUID
    franchise_id: UUID
    # 'manager' runs studios; 'reports' is view-only franchise reporting
    level: str = "manager"
    assigned_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class FranchiseOwnerUpdate(BaseModel):
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class FranchiseOwnerResponse(BaseModel):
    id: UUID
    level: str = "manager"
    # Human labels so the UI never shows raw ids
    user_name: str | None = None
    user_email: str | None = None
    user_id: UUID
    franchise_id: UUID
    assigned_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None
    is_active: bool
    assigned_at: datetime
    created_at: datetime
    updated_at: datetime
    # Phase 3: invite/onboarding status of the owner's User, derived from
    # invite_sent_at/password_set_at (see routes/franchise_owners.py).
    invited: bool = False
    accepted: bool = False

    model_config = {"from_attributes": True}
