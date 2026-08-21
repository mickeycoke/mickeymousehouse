"""Admin CRUD for the SaaS price book (pricing tiers admin feature). See
app/models/pricing_tier.py for the scope boundary — this is
platform-wide reference data, NOT per-studio billing (that's
StudioSubscription, untouched by this file).

All four endpoints are admin-only (Depends(require_admin)) — editing the
price book itself is not a studio-owner or manager concern.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.data.pricing_tiers import PricingTierRepo, pricing_tier_repo
from app.dependencies import require_admin
from app.models.user import User
from app.schemas.pricing_tier import (
    PricingTierCreate,
    PricingTierResponse,
    PricingTierUpdate,
)

router = APIRouter(prefix="/api/admin/pricing-tiers", tags=["pricing-tiers"])


@router.get("", response_model=List[PricingTierResponse])
def list_pricing_tiers(
    _: User = Depends(require_admin),
    repo: PricingTierRepo = Depends(pricing_tier_repo),
):
    return [PricingTierResponse.from_model(tier) for tier in repo.list_active()]


@router.post("", response_model=PricingTierResponse, status_code=status.HTTP_201_CREATED)
def create_pricing_tier(
    payload: PricingTierCreate,
    _: User = Depends(require_admin),
    repo: PricingTierRepo = Depends(pricing_tier_repo),
):
    tier = repo.create(**payload.model_dump())
    repo.db.commit()
    repo.db.refresh(tier)
    return PricingTierResponse.from_model(tier)


@router.put("/{tier_id}", response_model=PricingTierResponse)
def update_pricing_tier(
    tier_id: UUID,
    payload: PricingTierUpdate,
    _: User = Depends(require_admin),
    repo: PricingTierRepo = Depends(pricing_tier_repo),
):
    tier = repo.update(tier_id, **payload.model_dump(exclude_unset=True))
    repo.db.commit()
    repo.db.refresh(tier)
    return PricingTierResponse.from_model(tier)


@router.delete("/{tier_id}")
def delete_pricing_tier(
    tier_id: UUID,
    _: User = Depends(require_admin),
    repo: PricingTierRepo = Depends(pricing_tier_repo),
):
    repo.deactivate(tier_id)
    repo.db.commit()
    return {"message": "Pricing tier deactivated"}
