"""Stripe integration for the platform's OWN revenue: studios pay a recurring
monthly subscription.

This is the only module that imports `stripe`, and it imports it LAZILY
(inside each function) so the module — and therefore the whole app — loads
cleanly when the feature is off and `stripe` need never be touched.
`is_enabled()` is the single gate the routes consult.

Env (read at call time via `os.environ`, so the flag reflects the live
environment and tests can patch it):
  * BILLING_ENABLED         — truthy to arm the feature
  * STRIPE_SECRET_KEY       — the API key; also required for `is_enabled()`
  * STRIPE_WEBHOOK_SECRET   — the signing secret for the billing webhook
                              endpoint. Stripe signs each registered endpoint
                              with its own secret, so if you add more webhook
                              endpoints, give each its own env var.
"""
import logging
import os

from fastapi import HTTPException

logger = logging.getLogger("app.stripe_billing")

_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def is_enabled() -> bool:
    """True iff BILLING_ENABLED is truthy AND STRIPE_SECRET_KEY is set. Read
    fresh each call so flipping env (or a test monkeypatch) takes effect
    without a reimport."""
    return _truthy(os.environ.get("BILLING_ENABLED")) and bool(
        os.environ.get("STRIPE_SECRET_KEY")
    )


def create_subscription_checkout(*, subscription, studio, success_url: str, cancel_url: str):
    """Create a Stripe Checkout Session in subscription mode for one studio's
    contracted monthly price and return it (it carries `.id` and `.url`).

    Priced server-side off the already-set `subscription.contracted_amount_cents`
    (never trusted from the client): one recurring line item, priced inline via
    `price_data` (no pre-created Stripe Product/Price needed — inline pricing
    in subscription mode).
    `studio_subscription_id`/`studio_id` ride along in metadata so the webhook
    — which arrives with no session of its own — can find its way back to
    exactly this row.

    Never lets a Stripe error escape into the request path as a 500: a
    configuration/auth problem surfaces as a clean 502, a rejected request as
    a 400.
    """
    import stripe

    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    studio_display_name = studio.display_name or studio.name
    try:
        return stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price_data": {
                        "currency": subscription.currency,
                        "unit_amount": subscription.contracted_amount_cents,
                        "recurring": {"interval": "month"},
                        "product_data": {
                            "name": f"{studio_display_name} -- platform subscription",
                        },
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "studio_subscription_id": str(subscription.id),
                "studio_id": str(studio.id),
            },
            # Stripe does NOT copy a Checkout Session's metadata onto the
            # Subscription it creates — only this Session object would carry
            # it. Every event AFTER the first (renewal, payment failure,
            # cancellation) delivers the Subscription object itself, so
            # without this the webhook could resolve the first event and then
            # go permanently blind to every status change that follows.
            subscription_data={
                "metadata": {
                    "studio_subscription_id": str(subscription.id),
                    "studio_id": str(studio.id),
                },
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
        # A bad request (e.g. an invalid amount/currency) is the caller's
        # fault → 400; anything else (auth, connection, Stripe outage) is an
        # upstream failure → 502. Either way, a readable message, never a 500.
        logger.exception("Stripe subscription checkout session creation failed")
        status_code = 400 if isinstance(exc, stripe.error.InvalidRequestError) else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": "stripe_error", "message": "Could not start the subscription checkout."},
        )
    except Exception:  # noqa: BLE001 — nothing Stripe-shaped is allowed to 500 either
        logger.exception("Unexpected error creating Stripe subscription checkout session")
        raise HTTPException(
            status_code=502,
            detail={"code": "stripe_error", "message": "Could not start the subscription checkout."},
        )


def create_billing_portal_session(*, customer_id: str, return_url: str):
    """Create a Stripe Billing Portal session so a studio owner can fix a
    failed payment method themselves (self-serve owner Billing tab)
    — for `past_due`, the subscription already exists, so this
    is the right flow, not a fresh Checkout Session. Returns the session
    (it carries `.url`). Same never-500 error shape as
    `create_subscription_checkout`."""
    import stripe

    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    try:
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
    except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
        logger.exception("Stripe billing portal session creation failed")
        status_code = 400 if isinstance(exc, stripe.error.InvalidRequestError) else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": "stripe_error", "message": "Could not open the billing portal."},
        )
    except Exception:  # noqa: BLE001 — nothing Stripe-shaped is allowed to 500 either
        logger.exception("Unexpected error creating Stripe billing portal session")
        raise HTTPException(
            status_code=502,
            detail={"code": "stripe_error", "message": "Could not open the billing portal."},
        )


def construct_event(payload_bytes: bytes, sig_header: str):
    """Verify a webhook payload against STRIPE_WEBHOOK_SECRET and return the
    parsed event. Raises (`stripe.error.SignatureVerificationError` or
    `ValueError`) on a bad/absent signature or malformed body — the webhook
    route turns any raise here into a 400 and writes nothing."""
    import stripe

    return stripe.Webhook.construct_event(
        payload_bytes, sig_header, os.environ.get("STRIPE_WEBHOOK_SECRET")
    )
