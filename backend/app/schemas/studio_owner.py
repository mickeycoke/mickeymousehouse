from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class StudioOwnerCreate(BaseModel):
    user_id: UUID
    studio_id: UUID
    # 'owner' or 'manager' — a studio can have multiple managers
    level: str = "owner"
    assigned_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class StudioOwnerUpdate(BaseModel):
    # 'owner' or 'manager'. Was missing entirely, so PUT could never change a
    # person's role — the reason the UI had no way to change permissions.
    # Optional so a notes/active-only update leaves it be.
    level: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class StudioOwnerResponse(BaseModel):
    id: UUID
    level: str = "owner"
    # Human labels so the UI never shows raw ids
    user_name: str | None = None
    user_email: str | None = None
    user_id: UUID
    studio_id: UUID
    assigned_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None
    is_active: bool
    assigned_at: datetime
    created_at: datetime
    updated_at: datetime
    # Phase 2: invite/onboarding status of the owner's User, derived from
    # invite_sent_at/password_set_at (see routes/studio_owners.py).
    invited: bool = False
    accepted: bool = False

    model_config = {"from_attributes": True}
