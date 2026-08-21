"""Schemas for the self-serve owner Billing tab.
See `app/routes/owner_billing.py`."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OwnerBillingRow(BaseModel):
    """One of the caller's own studios, with enough to render the
    green/red dot and pick the right instructions/action — the derived
    `checkout_ready`/`has_payment_method` booleans save the frontend from
    re-deriving them from `contracted_amount_cents`/internal Stripe ids it
    has no other reason to see."""
    studio_id: UUID
    studio_name: str
    status: str
    current_period_end: Optional[datetime] = None
    # A price has been contracted (by an admin, today) — self-serve checkout
    # is possible. False means "not started, no price yet" -> contact us.
    checkout_ready: bool
    # A Stripe customer already exists (from a completed checkout) — the
    # Billing Portal (fix a failed payment method) is reachable.
    has_payment_method: bool
