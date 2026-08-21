import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class PricingTier(Base):
    """One row per SaaS price-book bracket. Genuinely platform-wide reference
    data: which bracket of active-client counts costs how much per month,
    the same price book for every studio.

    CRITICAL SCOPE BOUNDARY: this is NOT wired into actual per-studio
    billing. `StudioSubscription.contracted_amount_cents`
    (app/models/studio_subscription.py) is a separate, existing,
    hand-set-by-an-admin field — "v1 tiering is a human decision, not
    software" (that model's own comment). This table is the price BOOK
    itself: reference/config data an admin views and edits, independent of
    what any individual studio is actually charged. No foreign key or join
    to StudioSubscription or any studio table.

    MODEL_SCOPE: "unscoped: platform-wide pricing configuration; not tenant
    data, admin-only writes" (tests/test_data_layer_contract.py) — read and
    written only through app/data/pricing_tiers.py.

    `max_clients` NULL means open-ended (Enterprise, 300+ clients).
    `monthly_price_cents` NULL means "custom, negotiated" (Enterprise has no
    fixed price). `display_order` is the sort key both the admin screen and
    the GET endpoint use — independent of `min_clients` so a future
    re-ordering doesn't require renumbering brackets.
    """

    __tablename__ = "pricing_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    min_clients = Column(Integer, nullable=False)
    max_clients = Column(Integer, nullable=True)
    monthly_price_cents = Column(Integer, nullable=True)
    display_order = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
