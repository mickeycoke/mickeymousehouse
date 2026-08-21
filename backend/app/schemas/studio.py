from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class StudioBase(BaseModel):
    timezone: str = 'America/New_York'
    name: str
    display_name: Optional[str] = None
    short_name: Optional[str] = None
    notes: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    # Studio address. All nullable -- no studio has one today.
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class StudioCreate(StudioBase):
    # Admins may place the new studio in a franchise; franchise managers'
    # studios auto-join their own franchise regardless of this value.
    franchise_id: Optional[UUID] = None


class StudioUpdate(BaseModel):
    timezone: Optional[str] = None
    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    display_name: Optional[str] = None
    short_name: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    # Admin-only reassignment; None unassigns. Ignored for franchise managers.
    franchise_id: Optional[UUID] = None
    # Studio<->tier assignment: which pricing_tiers row this studio is
    # labeled as. None both means "field omitted" (exclude_unset, existing
    # convention below) AND "clear the assignment" when explicitly sent as
    # null — the route tells the two apart via `exclude_unset`.
    pricing_tier_id: Optional[UUID] = None
    # Studio address.
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class StudioResponse(StudioBase):
    id: UUID
    is_active: bool
    # Short self-serve onboarding code (Phase 1a). Read-only here — assigned by
    # the server so authorized staff can read it off and share it.
    onboard_code: Optional[str] = None
    # The studio's current active franchise link (None if unassigned).
    franchise_id: Optional[UUID] = None
    monthly_price: Optional[Decimal] = None
    # Studio<->tier assignment. None = no tier assigned.
    pricing_tier_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
