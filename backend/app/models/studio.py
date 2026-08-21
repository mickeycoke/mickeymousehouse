import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Studio(Base):
    __tablename__ = "studios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    # A short public code (e.g. entered on a shared-device kiosk, or as a
    # fallback self-serve onboarding code) — checked case-insensitively.
    short_name = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    timezone = Column(String(64), nullable=False, default="America/New_York")
    # Self-serve onboarding code (Phase 1a) — minted per studio, used to
    # resolve a studio from a code a user types (see utils/studio_lookup.py).
    onboard_code = Column(String(32), nullable=True)
    monthly_price = Column(Numeric(10, 2), nullable=True)
    # Studio<->tier assignment. Which price-book bracket
    # (app/models/pricing_tier.py) this studio is LABELED as — a manual,
    # admin-set classification, independent of what the studio is actually
    # billed (StudioSubscription.contracted_amount_cents, untouched by this
    # column). NULL = no tier assigned yet.
    pricing_tier_id = Column(UUID(as_uuid=True), ForeignKey("pricing_tiers.id"), nullable=True)
    # Studio address. All nullable -- no studio has one until filled in.
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(120), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
