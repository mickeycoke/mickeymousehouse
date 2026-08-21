"""Schemas for Stripe Studio Billing — the admin billing roster and its
actions. See `app/routes/studio_billing.py`."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class BillingConfigResponse(BaseModel):
    """GET /api/admin/billing/config — the frontend's on/off gate, mirroring
    `PaymentsConfigResponse`."""
    enabled: bool


class StudioBillingRow(BaseModel):
    """One row of the admin billing roster: every studio, with its
    (possibly not-yet-started) subscription state, plus the pricing tier
    it's labeled with."""
    studio_id: UUID
    studio_name: str
    contracted_amount_cents: Optional[int] = None
    currency: str
    status: str
    current_period_end: Optional[datetime] = None
    has_active_checkout: bool
    # F5 pricing tier this studio is labeled with (may be unassigned/custom).
    tier_name: Optional[str] = None
    tier_amount_cents: Optional[int] = None  # None = custom/negotiated or no tier


class SetContractedAmountRequest(BaseModel):
    amount_cents: int
    currency: str = "usd"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    # Set when the admin's "Send Checkout Link" also emailed the studio's
    # contact — the address it went to, so the UI can confirm it. None if the
    # studio had no contact email to send to.
    emailed_to: Optional[str] = None
