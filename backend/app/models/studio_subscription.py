import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class StudioSubscription(Base):
    """One row per studio's billing relationship with Stripe. Studios pay a
    recurring monthly subscription — this is the studio paying the platform.

    A row exists (`status='not_started'`, no Stripe ids) as soon as an admin
    contracts a price for the studio — before any Checkout session is ever
    created — so the admin billing screen can show every studio's contracted
    price up front. `studio_id` is unique: one studio, one active
    subscription.

    MODEL_SCOPE: "studio", read only through
    `app/data/studio_subscriptions.py`. Routes are admin-only (billing is
    platform revenue, not a studio-owner concern) — the studio scope still
    applies so a foreign studio's row is never reachable by id.

    Lifecycle: `stripe_customer_id`/`stripe_subscription_id` are set when the
    admin sends a Checkout link and the studio completes it. The billing
    webhook (never the browser redirect) updates `status` and
    `current_period_end` from `customer.subscription.*`/`invoice.*` events;
    `last_webhook_event_id` is the per-row dedupe key so a redelivered event
    is a no-op.
    """

    __tablename__ = "studio_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    studio_id = Column(UUID(as_uuid=True), ForeignKey("studios.id"), nullable=False, index=True, unique=True)
    # Hand-set by an admin — v1 tiering is a human decision, not software.
    # NULL until an admin contracts a price.
    contracted_amount_cents = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=False, default="usd")
    # 'not_started' | 'active' | 'past_due' | 'canceled' | 'incomplete'.
    status = Column(String(20), nullable=False, default="not_started")
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    stripe_checkout_session_id = Column(String(255), nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    # Set when the admin's "Send Checkout Link" email actually went out.
    # A studio owner sees NO billing surface until an amount is contracted
    # AND this email has been sent (or they already have a live
    # subscription) — see owner_billing.list_my_billing_studios.
    checkout_link_emailed_at = Column(DateTime, nullable=True)
    # Webhook dedupe key — the id of the last Stripe event applied to this row.
    last_webhook_event_id = Column(String(255), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
