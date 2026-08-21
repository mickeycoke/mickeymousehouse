from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FranchiseStudioCreate(BaseModel):
    franchise_id: UUID
    studio_id: UUID
    assigned_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class FranchiseStudioUpdate(BaseModel):
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class FranchiseStudioResponse(BaseModel):
    id: UUID
    franchise_id: UUID
    studio_id: UUID
    assigned_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None
    is_active: bool
    assigned_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
