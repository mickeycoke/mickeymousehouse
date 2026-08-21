from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FranchiseBase(BaseModel):
    name: str
    description: Optional[str] = None
    display_order: Optional[int] = None
    notes: Optional[str] = None


class FranchiseCreate(FranchiseBase):
    pass


class FranchiseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class FranchiseResponse(FranchiseBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
