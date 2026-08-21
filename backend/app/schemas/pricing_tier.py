from typing import Optional
from uuid import UUID

from pydantic import BaseModel


def compute_per_client_rate_at_cap(
    monthly_price_cents: Optional[int], max_clients: Optional[int]
) -> Optional[float]:
    """monthly_price_cents / 100 / max_clients, rounded to 2 decimals.

    Null whenever max_clients OR monthly_price_cents is null (Enterprise —
    open-ended cap, custom/negotiated price — can't compute either way).

    $0 is treated as a real, computable rate (0.0), NOT as "uncomputable" —
    only an actual None on either input produces a null result. Free
    (monthly_price_cents=0, max_clients=1) therefore reads back 0.0, not
    null, exercised explicitly in tests/test_pricing_tiers.py.
    """
    if max_clients is None or monthly_price_cents is None:
        return None
    return round((monthly_price_cents / 100) / max_clients, 2)


class PricingTierCreate(BaseModel):
    name: str
    min_clients: int
    max_clients: Optional[int] = None
    monthly_price_cents: Optional[int] = None
    display_order: int


class PricingTierUpdate(BaseModel):
    name: Optional[str] = None
    min_clients: Optional[int] = None
    max_clients: Optional[int] = None
    monthly_price_cents: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class PricingTierResponse(BaseModel):
    id: UUID
    name: str
    min_clients: int
    max_clients: Optional[int] = None
    monthly_price_cents: Optional[int] = None
    display_order: int
    is_active: bool
    # Server-computed, never stored — see compute_per_client_rate_at_cap.
    per_client_rate_at_cap: Optional[float] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, tier) -> "PricingTierResponse":
        """Build the response including the computed field. Computed here
        (not via a pydantic validator) because the rate isn't an attribute
        on the ORM object — from_attributes alone can't populate it."""
        return cls(
            id=tier.id,
            name=tier.name,
            min_clients=tier.min_clients,
            max_clients=tier.max_clients,
            monthly_price_cents=tier.monthly_price_cents,
            display_order=tier.display_order,
            is_active=tier.is_active,
            per_client_rate_at_cap=compute_per_client_rate_at_cap(
                tier.monthly_price_cents, tier.max_clients
            ),
        )
