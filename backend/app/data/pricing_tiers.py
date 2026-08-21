"""Pricing tier reads/writes (pricing tiers admin feature).

`PricingTier` is genuinely platform-wide reference data (MODEL_SCOPE:
"unscoped: platform-wide pricing configuration; not tenant data, admin-only
writes" in tests/test_data_layer_contract.py) — it carries no `studio_id`
or `franchise_id`, so this repo does NOT subclass `StudioScopedRepo` /
`FranchiseScopedRepo`: those exist to filter rows by a caller's scope, and
there is nothing to filter here. Every route that touches this repo is
already gated by `Depends(require_admin)`, so no `AccessScope` is needed to
construct it either.

It exists as a repo at all — rather than routes querying `PricingTier`
directly, which the data-layer contract test would permit for an unscoped
model — to keep every query for this table in one place, matching this
repo's "queries live in app/data/" convention (CLAUDE.md).
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.dependencies import get_db
from app.models.pricing_tier import PricingTier


class PricingTierRepo:
    model = PricingTier
    not_found_detail = "Pricing tier not found"

    def __init__(self, db: DBSession):
        self.db = db

    def query(self):
        return self.db.query(PricingTier)

    def list_active(self):
        """Active tiers only, ordered by display_order — the GET
        /api/admin/pricing-tiers contract's exact sort. A deactivated
        (soft-deleted) tier drops out of this list; there is no reactivate
        endpoint in the API contract, matching DELETE being a one-way soft
        delete here (same convention as app/routes/users.py's delete_user)."""
        return (
            self.query()
            .filter(PricingTier.is_active == True)  # noqa: E712
            .order_by(PricingTier.display_order.asc())
            .all()
        )

    def get(self, id_: UUID) -> Optional[PricingTier]:
        return self.query().filter(PricingTier.id == id_).first()

    def get_or_404(self, id_: UUID) -> PricingTier:
        tier = self.get(id_)
        if tier is None:
            raise HTTPException(status_code=404, detail=self.not_found_detail)
        return tier

    def create(self, **kwargs) -> PricingTier:
        tier = PricingTier(**kwargs)
        self.db.add(tier)
        self.db.flush()
        return tier

    def update(self, id_: UUID, **kwargs) -> PricingTier:
        tier = self.get_or_404(id_)
        for field, value in kwargs.items():
            setattr(tier, field, value)
        self.db.flush()
        return tier

    def deactivate(self, id_: UUID) -> PricingTier:
        tier = self.get_or_404(id_)
        tier.is_active = False
        self.db.flush()
        return tier


def pricing_tier_repo(db: DBSession = Depends(get_db)) -> PricingTierRepo:
    return PricingTierRepo(db)
