"""Self-serve owner Billing tab — a studio
owner or franchise owner's OWN view of their studio(s)' Stripe Studio
Billing subscription, separate from the admin-only central roster in
`app/routes/studio_billing.py`.

Three endpoints, all requiring a logged-in non-admin owner (admins use the
admin roster instead):
  * GET  /api/billing/my-studios                                  — my studio(s) + status
  * POST /api/billing/my-studios/{id}/checkout-session             — self-serve: start/resume billing
  * POST /api/billing/my-studios/{id}/billing-portal-session       — self-serve: fix a failed payment

"My studio(s)" is `get_owned_billing_studio_ids` — OWNER level only (never
manager), and a franchise owner's studios ARE included (a deliberate,
feature-specific exception to the usual franchise/studio tier separation;
see that function's docstring). Every route checks the requested studio_id
against that set itself (403 if outside it, matching the existing pattern in
`routes/studios.py`'s single-studio GET) rather than relying solely on the
repo layer, since the repo's scope enforcement only fires on writes that
don't already exist for that studio.
"""
import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.data.scope import AccessScope
from app.data.studio_subscriptions import StudioSubscriptionRepo
from app.dependencies import get_current_user, get_db
from app.models.studio import Studio
from app.models.user import User
from app.routes.studio_billing import _create_checkout_session_for_studio
from app.schemas.owner_billing import OwnerBillingRow
from app.schemas.studio_billing import CheckoutSessionResponse
from app.services import stripe_billing
from app.utils.ownership import get_owned_billing_studio_ids

router = APIRouter(prefix="/api/billing", tags=["owner-billing"])


class BillingPortalSessionResponse(CheckoutSessionResponse):
    """Same shape as a Checkout Session response (one URL to send the caller
    to) — a distinct name because it's conceptually a different action."""


def _owned_subscriptions_repo(db: DBSession, user: User) -> tuple[StudioSubscriptionRepo, set]:
    """Build a StudioSubscriptionRepo manually scoped to this user's OWNED
    billing studios — deliberately NOT the standard `get_scope` dependency,
    whose franchise/studio visibility rules are different (and narrower:
    franchise ownership does not include studio access there by design).
    Returns the repo plus the raw owned-id set for the route's own 403 check."""
    owned_ids = get_owned_billing_studio_ids(db, user)
    scope = AccessScope(
        user=user,
        operating_studio_id=None,
        visible_studio_ids=frozenset(owned_ids),
        visible_franchise_id=None,
    )
    return StudioSubscriptionRepo(db, scope), owned_ids


def _require_owned_studio(db: DBSession, studio_id: UUID, owned_ids: set) -> Studio:
    if studio_id not in owned_ids:
        raise HTTPException(status_code=403, detail="Studio is outside your ownership scope")
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if studio is None:
        raise HTTPException(status_code=404, detail="Studio not found")
    return studio


@router.get("/my-studios", response_model=list[OwnerBillingRow])
def list_my_billing_studios(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscriptions, owned_ids = _owned_subscriptions_repo(db, current_user)
    if not owned_ids:
        return []
    studios = {
        s.id: s
        for s in db.query(Studio).filter(Studio.id.in_(owned_ids), Studio.is_active == True).all()
    }
    rows = []
    for studio_id, studio in studios.items():
        # No billing surface until the admin has BOTH set a contracted amount
        # AND sent the checkout email — except a studio
        # that already has a live subscription history (active/past_due/
        # canceled), which must always see its own billing to manage it. Also
        # deliberately get (not get_or_create): listing must not mint rows.
        subscription = subscriptions.get_by_studio(studio_id)
        if subscription is None:
            continue
        invited = bool(
            subscription.contracted_amount_cents
            and subscription.contracted_amount_cents > 0
            and subscription.checkout_link_emailed_at is not None
        )
        if not invited and subscription.status == "not_started":
            continue
        rows.append(
            OwnerBillingRow(
                studio_id=studio.id,
                studio_name=studio.display_name or studio.name,
                status=subscription.status,
                current_period_end=subscription.current_period_end,
                checkout_ready=bool(
                    subscription.contracted_amount_cents and subscription.contracted_amount_cents > 0
                ),
                has_payment_method=subscription.stripe_customer_id is not None,
            )
        )
    db.commit()
    return sorted(rows, key=lambda r: r.studio_name)


@router.post(
    "/my-studios/{studio_id}/checkout-session",
    response_model=CheckoutSessionResponse,
)
def create_my_checkout_session(
    studio_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscriptions, owned_ids = _owned_subscriptions_repo(db, current_user)
    studio = _require_owned_studio(db, studio_id, owned_ids)
    subscription = subscriptions.get_or_create_for_studio(studio_id)

    base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    return _create_checkout_session_for_studio(
        db, studio, subscription, subscriptions,
        success_url=f"{base}/billing?checkout=success",
        cancel_url=f"{base}/billing?checkout=cancelled",
    )


@router.post(
    "/my-studios/{studio_id}/billing-portal-session",
    response_model=BillingPortalSessionResponse,
)
def create_my_billing_portal_session(
    studio_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The `past_due` fix-your-payment-method flow: Stripe's own Billing
    Portal, not a fresh Checkout — a subscription already exists."""
    if not stripe_billing.is_enabled():
        raise HTTPException(status_code=409, detail={"code": "billing_disabled"})

    subscriptions, owned_ids = _owned_subscriptions_repo(db, current_user)
    studio = _require_owned_studio(db, studio_id, owned_ids)
    subscription = subscriptions.get_by_studio(studio_id)
    if subscription is None or not subscription.stripe_customer_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "no_stripe_customer",
                "message": "There's no billing history for this studio yet.",
            },
        )

    base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    session = stripe_billing.create_billing_portal_session(
        customer_id=subscription.stripe_customer_id,
        return_url=f"{base}/billing",
    )
    return BillingPortalSessionResponse(checkout_url=session.url)
