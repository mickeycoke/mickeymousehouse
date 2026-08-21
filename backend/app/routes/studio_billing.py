"""Stripe Studio Billing routes — the platform's OWN
revenue: studios pay a recurring monthly subscription.

Five endpoints, all admin-only except the config gate and the webhook:
  * GET  /api/admin/billing/config                                — on/off gate, no auth
  * GET  /api/admin/billing/studios                                — admin: the billing roster
    (optional `?franchise_id=` narrows it to that franchise's studios)
  * POST /api/admin/billing/studios/{id}/contracted-amount         — admin: set the price
  * POST /api/admin/billing/studios/{id}/checkout-session          — admin: send a Checkout link
  * POST /api/webhooks/stripe/billing                              — PUBLIC: billing truth

Self-serve owner-facing routes (`/api/billing/...`) live separately in
`app/routes/owner_billing.py` — same underlying
`StudioSubscription`/`stripe_billing` machinery, different audience and
auth model. `_create_checkout_session_for_studio` below is shared by both.

All Stripe access goes through `app/services/stripe_billing.py`. Status
derives from the webhook, NEVER the browser redirect.
"""
import logging
import os
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DBSession

from app.data.franchise_studio_repo import FranchiseStudioRepo, franchise_studio_repo
from app.data.pricing_tiers import PricingTierRepo
from app.data.scope import AccessScope
from app.data.studio_subscriptions import StudioSubscriptionRepo, studio_subscription_repo
from app.dependencies import get_db, require_admin
from app.models.studio import Studio
from app.models.user import User
from app.schemas.studio_billing import (
    BillingConfigResponse,
    CheckoutSessionResponse,
    SetContractedAmountRequest,
    StudioBillingRow,
)
from app.services import email as email_service
from app.services import stripe_billing

logger = logging.getLogger("app.studio_billing")

router = APIRouter(tags=["studio-billing"])

# Stripe subscription statuses -> this app's own status vocabulary
# ('not_started'|'active'|'past_due'|'canceled'|'incomplete'). trialing counts
# as active (v1 has no trial concept of its own, but Stripe may still report
# it); unpaid is treated like past_due (money owed, not yet given up on);
# incomplete_expired is a dead subscription that never activated -> canceled.
_STRIPE_STATUS_MAP = {
    "active": "active",
    "trialing": "active",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "past_due",
    "incomplete": "incomplete",
    "incomplete_expired": "canceled",
}

_SUBSCRIPTION_EVENT_TYPES = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
)


@router.get("/api/admin/billing/config", response_model=BillingConfigResponse)
def billing_config():
    """The frontend's gate for whether to show any Billing UI. Reveals only
    the global on/off state, so it needs no auth (mirrors
    GET /api/payments/config)."""
    return BillingConfigResponse(enabled=stripe_billing.is_enabled())


@router.get("/api/admin/billing/studios", response_model=list[StudioBillingRow])
def list_billing_studios(
    franchise_id: Optional[UUID] = None,
    db: DBSession = Depends(get_db),
    _: User = Depends(require_admin),
    subscriptions: StudioSubscriptionRepo = Depends(studio_subscription_repo),
    franchise_studios: FranchiseStudioRepo = Depends(franchise_studio_repo),
):
    """Every ACTIVE studio, each with its (possibly not-yet-started)
    subscription row. This is the one place allowed to see every studio at
    once — it's the admin billing roster, and billing is platform revenue,
    not a per-studio concern. `Studio` itself is registered "unscoped" in
    the data-layer contract (the studio directory; membership is what
    scopes), so reading it directly here is not a violation.

    Filtered to is_active=True: a database can accumulate a lot of test/demo
    data and deactivated imports over time, and an unfiltered roster would be
    unusable against that. A newly created active studio shows up here
    automatically on next load, since this is a live query, not a
    cached/curated list.

    `franchise_id`: optional — narrows the roster to studios linked to that
    franchise via the `franchise_studios`
    association, read through `FranchiseStudioRepo` (never a raw query here;
    `FranchiseStudio` is a scoped model in the data-layer contract). Omitted
    means every active studio, unchanged from before this param existed. An
    unknown franchise_id yields an empty roster rather than an error — same
    "no existence check on an optional filter" convention as
    `GET /api/franchise-studios?franchise_id=`."""
    studios_query = db.query(Studio).filter(Studio.is_active == True)
    if franchise_id is not None:
        franchise_studio_ids = franchise_studios.list_studio_ids_for_franchise(franchise_id)
        # Explicit `.filter(False)` on empty, same as StudioScopedRepo._apply_scope:
        # a deliberate "see nothing" rather than an empty (and SQLAlchemy-flagged) IN().
        studios_query = (
            studios_query.filter(Studio.id.in_(franchise_studio_ids))
            if franchise_studio_ids
            else studios_query.filter(False)
        )
    studios = studios_query.order_by(Studio.name).all()

    tiers_by_id = {t.id: t for t in PricingTierRepo(db).list_active()}

    rows = []
    for studio in studios:
        subscription = subscriptions.get_or_create_for_studio(studio.id)
        tier = tiers_by_id.get(studio.pricing_tier_id)
        rows.append(_billing_row(studio, subscription, tier))
    db.commit()
    return rows


def _billing_row(studio: Studio, subscription, tier) -> StudioBillingRow:
    """One roster row. Shared by the list endpoint and set-contracted-amount so
    a single-row update returns the SAME complete shape (tier included), not a
    stripped row that would blank the UI's pills/tier on save. `tier` is the
    studio's manually-assigned pricing_tier_id (see app/models/studio.py),
    None if unassigned."""
    return StudioBillingRow(
        studio_id=studio.id,
        studio_name=studio.display_name or studio.name,
        contracted_amount_cents=subscription.contracted_amount_cents,
        currency=subscription.currency,
        status=subscription.status,
        current_period_end=subscription.current_period_end,
        has_active_checkout=subscription.stripe_checkout_session_id is not None,
        tier_name=tier.name if tier else None,
        tier_amount_cents=tier.monthly_price_cents if tier else None,
    )


@router.post(
    "/api/admin/billing/studios/{studio_id}/contracted-amount",
    response_model=StudioBillingRow,
)
def set_contracted_amount(
    studio_id: UUID,
    payload: SetContractedAmountRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    subscriptions: StudioSubscriptionRepo = Depends(studio_subscription_repo),
):
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if studio is None:
        raise HTTPException(status_code=404, detail="Studio not found")

    subscription = subscriptions.get_or_create_for_studio(studio_id)
    subscription = subscriptions.set_contracted_amount(
        subscription,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        created_by_user_id=current_user.id,
    )
    db.commit()
    tier = PricingTierRepo(db).get(studio.pricing_tier_id) if studio.pricing_tier_id else None
    return _billing_row(studio, subscription, tier)


def _create_checkout_session_for_studio(
    db: DBSession,
    studio: Studio,
    subscription,
    subscriptions: StudioSubscriptionRepo,
    *,
    success_url: str,
    cancel_url: str,
) -> CheckoutSessionResponse:
    """Shared by the admin route below and the owner self-serve route in
    `owner_billing.py` — same checks (billing enabled, a price already
    contracted), same Stripe call, same commit. Callers own the studio/
    subscription lookup and any auth/ownership check first."""
    if not stripe_billing.is_enabled():
        raise HTTPException(status_code=409, detail={"code": "billing_disabled"})
    if not subscription.contracted_amount_cents or subscription.contracted_amount_cents <= 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "no_contracted_amount",
                "message": "Set a price before sending a checkout link.",
            },
        )

    session = stripe_billing.create_subscription_checkout(
        subscription=subscription,
        studio=studio,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    subscriptions.attach_checkout(subscription, checkout_session_id=session.id)
    db.commit()

    return CheckoutSessionResponse(checkout_url=session.url)


@router.post(
    "/api/admin/billing/studios/{studio_id}/checkout-session",
    response_model=CheckoutSessionResponse,
)
def create_checkout_session(
    studio_id: UUID,
    db: DBSession = Depends(get_db),
    _: User = Depends(require_admin),
    subscriptions: StudioSubscriptionRepo = Depends(studio_subscription_repo),
):
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if studio is None:
        raise HTTPException(status_code=404, detail="Studio not found")

    subscription = subscriptions.get_or_create_for_studio(studio_id)
    base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    resp = _create_checkout_session_for_studio(
        db, studio, subscription, subscriptions,
        success_url=f"{base}/setup/billing?checkout=success",
        cancel_url=f"{base}/setup/billing?checkout=cancelled",
    )
    # The button EMAILS the studio owner the link (with their tier + monthly
    # cost), rather than just handing the admin a raw Stripe URL to forward
    # by hand. The URL is still returned so the admin can copy it if they
    # want (shown below the button).
    resp.emailed_to = _email_checkout_link(db, studio, subscription, resp.checkout_url)
    return resp


def _email_checkout_link(db: DBSession, studio: Studio, subscription, checkout_url: str):
    """Best-effort: email the studio's contact the checkout link + tier/cost.
    Returns the address emailed, or None if the studio has no contact email.
    Never raises — a send failure must not fail the (already-created) checkout
    session; matches the log-and-swallow pattern used by the other billing
    emails."""
    if not studio.contact_email:
        return None
    tier = PricingTierRepo(db).get(studio.pricing_tier_id) if studio.pricing_tier_id else None
    cents = subscription.contracted_amount_cents or 0
    cost_display = f"${cents / 100:.2f}/month"
    try:
        email_service.send_billing_checkout_email(
            studio.contact_email,
            studio.display_name or studio.name,
            tier.name if tier else None,
            cost_display,
            checkout_url,
        )
        # This send is what unlocks the studio owner's self-serve Billing tab
        # (owner_billing.list_my_billing_studios requires amount + this
        # marker). Recorded only on a successful send.
        subscription.checkout_link_emailed_at = datetime.utcnow()
        db.commit()
        return studio.contact_email
    except Exception as exc:  # noqa: BLE001 — a send failure must not fail checkout
        logger.error(
            "billing checkout email FAILED for studio %s (%s): %s",
            studio.id, studio.contact_email, email_service.describe_send_failure(exc),
        )
        return None


@router.post("/api/webhooks/stripe/billing")
async def stripe_billing_webhook(request: Request, db: DBSession = Depends(get_db)):
    """PUBLIC, unauthenticated — Stripe calls it directly. Authenticity is the
    signature, not a login: the raw body is verified against
    STRIPE_WEBHOOK_SECRET, and a bad/absent signature is a 400 that
    writes nothing. This is where a studio's subscription status becomes
    truth — NEVER the browser redirect.

    No logged-in user, so this builds an unrestricted admin-equivalent scope
    (`user=None, operating_studio_id=None, visible_studio_ids=None,
    visible_franchise_id=None`) before touching the repo. Safe because
    `StudioScopedRepo.query()`/`_apply_scope` never dereferences `scope.user`
    (only `FranchiseScopedRepo` does) — confirmed for `StudioSubscriptionRepo`
    specifically since this is the one webhook in the app resolving a row by
    metadata alone, with no single studio to pin the scope to up front.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe_billing.construct_event(payload, sig_header)
    except Exception:  # noqa: BLE001 — any verify/parse failure is a flat 400
        logger.warning("Rejected a Stripe billing webhook with a bad/absent signature")
        return Response(status_code=400)

    event_type = event["type"]
    obj = event["data"]["object"]
    metadata = obj.get("metadata") or {}
    subscription_id_raw = metadata.get("studio_subscription_id")

    scope = AccessScope(
        user=None,
        operating_studio_id=None,
        visible_studio_ids=None,
        visible_franchise_id=None,
    )
    subscriptions = StudioSubscriptionRepo(db, scope)

    subscription = None
    if subscription_id_raw:
        try:
            subscription = subscriptions.get(UUID(subscription_id_raw))
        except (ValueError, TypeError):
            subscription = None

    if subscription is None:
        # Metadata missing/invalid, or pointed at a row that's gone. Fall back
        # to the Stripe subscription id — every event type here except
        # checkout.session.completed carries the Subscription object itself
        # (obj.id) or references it (obj.subscription); a row only has
        # stripe_subscription_id stamped after its OWN first webhook, so this
        # only helps events after the first, which is exactly when metadata
        # would otherwise be the only path. Defense-in-depth: the
        # subscription_data.metadata passed at Checkout creation already
        # makes every customer.subscription.* event carry the metadata
        # directly, so this fallback should rarely be needed in practice.
        fallback_subscription_id = obj.get("subscription") or (
            obj.get("id") if event_type != "checkout.session.completed" else None
        )
        if fallback_subscription_id:
            subscription = subscriptions.get_by_stripe_subscription_id(fallback_subscription_id)

    if subscription is None:
        # Not one of ours, or a row we can't resolve by any path — ack and
        # move on rather than erroring.
        return Response(status_code=200)

    # Idempotency: this exact event already applied to this row -> no-op.
    if subscription.last_webhook_event_id == event["id"]:
        return Response(status_code=200)

    if event_type in _SUBSCRIPTION_EVENT_TYPES:
        raw_status = obj.get("status")
        if raw_status is not None:
            new_status = _STRIPE_STATUS_MAP.get(raw_status, "incomplete")
        elif event_type == "checkout.session.completed":
            # A Checkout Session has no .status field of its own; completing
            # it for a subscription means the subscription started.
            new_status = "active"
        else:
            new_status = subscription.status
    elif event_type == "customer.subscription.deleted":
        new_status = "canceled"
    else:
        # Unknown/uninteresting event type -> ack, no-op.
        return Response(status_code=200)

    stripe_customer_id = obj.get("customer")
    # A Subscription object IS itself the subscription (no separate
    # "subscription" field); a Checkout Session carries it under "subscription".
    stripe_subscription_id = obj.get("subscription") or (
        obj.get("id") if event_type != "checkout.session.completed" else None
    )

    current_period_end_raw = obj.get("current_period_end")
    if current_period_end_raw is None:
        # Stripe API versions since 2025-03-31 carry current_period_end on the
        # subscription items, not the Subscription itself: sub.current_period_end
        # is null, item.current_period_end is set.
        items = (obj.get("items") or {}).get("data") or []
        if items:
            current_period_end_raw = items[0].get("current_period_end")
    current_period_end = (
        datetime.utcfromtimestamp(current_period_end_raw)
        if current_period_end_raw is not None
        else subscription.current_period_end
    )

    old_status = subscription.status
    subscriptions.apply_webhook_status(
        subscription,
        status=new_status,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        current_period_end=current_period_end,
        event_id=event["id"],
    )
    db.commit()

    # Notify the studio on a genuine transition INTO a payment-problem state
    # — not on every redelivery of an event that already applied (idempotency
    # check above already excludes that) and not on every unrelated status
    # write.
    if new_status in ("past_due", "canceled") and new_status != old_status:
        _notify_billing_payment_issue(db, subscription.studio_id, new_status)

    return Response(status_code=200)


def _notify_billing_payment_issue(db: DBSession, studio_id, status: str) -> None:
    """Best-effort notification email on a past_due/canceled transition.
    Never raises — this runs after the webhook's own commit already
    succeeded, so a send failure must not turn a 200 ack into an error
    (Stripe would just retry the same event, which idempotency would then
    no-op anyway). Mirrors `_notify_pricing_tier_changed` in
    `routes/studios.py`."""
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if studio is None or not studio.contact_email:
        logger.warning(
            "Studio subscription %s -> %s but studio %s has no contact_email; "
            "skipping notification email.", status, studio_id, studio_id,
        )
        return
    try:
        email_service.send_billing_payment_issue_email(
            studio.contact_email, studio.display_name or studio.name, status,
        )
    except Exception as exc:  # noqa: BLE001 — a send failure must not affect the webhook ack
        logger.error(
            "billing payment-issue email FAILED for studio %s (%s): %s",
            studio.id, studio.contact_email, email_service.describe_send_failure(exc),
        )
