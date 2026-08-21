"""Studio billing reads/writes (Stripe Studio Billing).

Studio-scoped like `ClientPackagePurchase` — every `StudioSubscription`
carries its own `studio_id`. Routes that use this repo are admin-only (billing
is platform revenue, not a studio-owner concern), and an admin's scope sees
every studio — so `.all()` here is the admin billing screen's studio list, and
`get_or_404` on a foreign studio still 404s cleanly if ever called
non-admin. All queries touching `StudioSubscription` live here; routes stay
thin.

The billing webhook has no logged-in user, same constraint as the Client
Payments webhook — it must build an admin-equivalent (or single-studio) scope
before reaching these methods rather than querying the model directly.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session as DBSession

from app.data.base import StudioScopedRepo
from app.data.scope import AccessScope, get_scope
from app.dependencies import get_db
from app.models.studio_subscription import StudioSubscription


class StudioSubscriptionRepo(StudioScopedRepo):
    model = StudioSubscription
    not_found_detail = "Studio subscription not found"

    def get_by_studio(self, studio_id: UUID) -> Optional[StudioSubscription]:
        return self.query().filter(StudioSubscription.studio_id == studio_id).first()

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> Optional[StudioSubscription]:
        """The webhook's lookup path: find the row for a Stripe subscription
        event. Scoped like every read here."""
        return (
            self.query()
            .filter(StudioSubscription.stripe_subscription_id == stripe_subscription_id)
            .first()
        )

    def get_or_create_for_studio(self, studio_id: UUID) -> StudioSubscription:
        """A row always exists once an admin looks at a studio's billing, even
        before any price is contracted — so the admin screen can list every
        studio with a place to set a price, not just the ones already billed."""
        existing = self.get_by_studio(studio_id)
        if existing:
            return existing
        row = self.stamp_new(studio_id=studio_id, status="not_started", currency="usd")
        self.db.add(row)
        self.db.flush()
        return row

    def set_contracted_amount(
        self, subscription: StudioSubscription, *, amount_cents: int, currency: str, created_by_user_id: Optional[UUID]
    ) -> StudioSubscription:
        subscription.contracted_amount_cents = amount_cents
        subscription.currency = currency
        subscription.created_by_user_id = created_by_user_id
        self.db.flush()
        return subscription

    def attach_checkout(self, subscription: StudioSubscription, *, checkout_session_id: str) -> StudioSubscription:
        subscription.stripe_checkout_session_id = checkout_session_id
        self.db.flush()
        return subscription

    def apply_webhook_status(
        self,
        subscription: StudioSubscription,
        *,
        status: str,
        stripe_customer_id: Optional[str],
        stripe_subscription_id: Optional[str],
        current_period_end: Optional[datetime],
        event_id: str,
    ) -> StudioSubscription:
        """Idempotent status update from the billing webhook. Callers must
        check `last_webhook_event_id == event_id` themselves before calling
        this if they need a hard redelivery no-op; Stripe's own event
        ordering plus this always-latest-wins update keeps status correct
        even if events arrive out of order for terminal states, since every
        Stripe event carries the subscription's full current state."""
        subscription.status = status
        if stripe_customer_id:
            subscription.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            subscription.stripe_subscription_id = stripe_subscription_id
        subscription.current_period_end = current_period_end
        subscription.last_webhook_event_id = event_id
        self.db.flush()
        return subscription

    def list_all(self):
        """Every studio's subscription row, for the admin billing screen.
        Only meaningful for an admin scope (unrestricted `.query()`)."""
        return self.query().order_by(StudioSubscription.created_at.asc()).all()


def studio_subscription_repo(
    db: DBSession = Depends(get_db), scope: AccessScope = Depends(get_scope)
) -> StudioSubscriptionRepo:
    return StudioSubscriptionRepo(db, scope)
