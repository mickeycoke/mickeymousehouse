"""Stripe Studio Billing — the platform's OWN revenue:
studios pay a recurring monthly subscription. See
`app/routes/studio_billing.py`.

Admin-only. Stripe is NEVER touched here: `stripe` is not imported and no
key/network is used. The two
seams the routes/webhook consult through `app.services.stripe_billing` are
monkeypatched:

  * is_enabled()                    — the global on/off gate
  * create_subscription_checkout()  — returns a fake object carrying `.id`/`.url`
  * construct_event()               — returns a fake, already-"verified" event dict

This proves: the disabled-feature responses, admin-only access on every
route, the roster auto-creating a `not_started` row per studio, setting a
contracted price, a checkout session requiring that price first, and the
webhook driving status to active/canceled with exactly-once idempotency on
event redelivery plus a bad signature writing nothing.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from app.models.franchise_owner import FranchiseOwner
from app.models.pricing_tier import PricingTier
from app.models.studio import Studio
from app.models.studio_subscription import StudioSubscription
from app.models.user import User
from app.utils.password import hash_password

from app.services import email as email_module
from app.services import stripe_billing


# ─── cleanup ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _cleanup(db):
    yield
    db.rollback()
    db.query(StudioSubscription).delete()
    db.query(FranchiseOwner).delete()
    db.query(Studio).filter(Studio.pricing_tier_id.isnot(None)).update({"pricing_tier_id": None})
    db.query(PricingTier).delete()
    db.commit()


# ─── world builders ──────────────────────────────────────────────────────

def _studio(db, label):
    s = Studio(name=f"{label}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _tier(db, label, cents=8000):
    t = PricingTier(name=f"{label}-{uuid.uuid4().hex[:6]}", min_clients=0,
                    monthly_price_cents=cents, display_order=0, is_active=True)
    db.add(t); db.commit(); db.refresh(t)
    return t


def _instructor(db, label):
    """A plain login-capable non-admin user (role='instructor')."""
    u = User(email=f"{label}-{uuid.uuid4().hex[:8]}@billingtests.com", name=label,
             password_hash=hash_password("password123"), role="instructor", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _franchise_manager(db, label):
    """A login-capable user who manages a franchise (level='manager') but is
    NOT an admin -- franchise management is a different axis than the admin
    role, and require_admin only ever checks role == 'admin'."""
    from app.models.franchise import Franchise
    u = _instructor(db, label)
    franchise = Franchise(name=f"Fran-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(franchise); db.commit()
    db.add(FranchiseOwner(user_id=u.id, franchise_id=franchise.id, level="manager", is_active=True))
    db.commit()
    return u


def _login(client, user):
    r = client.post("/api/auth/login", json={"email": user.email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ─── stripe seam fakes ─────────────────────────────────────────────────────

class _FakeCheckoutSession:
    """Stand-in for a Stripe Checkout Session — the route only reads `.id`/`.url`."""
    def __init__(self, id, url):
        self.id = id
        self.url = url


def _subscription_event(*, event_id, event_type, status, studio_subscription_id,
                        stripe_subscription_id="sub_test_1", stripe_customer_id="cus_test_1",
                        current_period_end=None):
    """A `customer.subscription.*` event shaped exactly as the webhook reads
    it: `event["id"]`, `event["type"]`, `event["data"]["object"]` with
    `.get("metadata")`, `.get("status")`, `.get("customer")`, and the object's
    own id doubling as the subscription id (no separate "subscription" field
    for a Subscription object itself)."""
    obj = {
        "id": stripe_subscription_id,
        "status": status,
        "customer": stripe_customer_id,
        "metadata": {"studio_subscription_id": str(studio_subscription_id)},
    }
    if current_period_end is not None:
        obj["current_period_end"] = int(current_period_end.timestamp())
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


def _subscription_event_with_item_period_end(*, item_current_period_end, **kwargs):
    """Stripe API versions since 2025-03-31 put current_period_end on each
    subscription item, NOT on the Subscription object. Same event shape,
    period end nested in items."""
    event = _subscription_event(**kwargs)
    event["data"]["object"]["items"] = {
        "data": [{"current_period_end": int(item_current_period_end.timestamp())}],
    }
    return event


def _checkout_completed_event(*, event_id, studio_subscription_id,
                              stripe_subscription_id="sub_test_1", stripe_customer_id="cus_test_1",
                              session_id="cs_test_1"):
    """`checkout.session.completed` — a Checkout Session has no `.status` of
    its own; the subscription id rides in `.subscription`, not `.id`."""
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "customer": stripe_customer_id,
                "subscription": stripe_subscription_id,
                "metadata": {"studio_subscription_id": str(studio_subscription_id)},
            }
        },
    }


def _deleted_event(*, event_id, studio_subscription_id, stripe_subscription_id="sub_test_1"):
    return {
        "id": event_id,
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": stripe_subscription_id,
                "metadata": {"studio_subscription_id": str(studio_subscription_id)},
            }
        },
    }


@pytest.fixture
def billing_on(monkeypatch):
    """Arm the feature and stub Stripe checkout creation. `is_enabled` is
    patched ON THE MODULE the routes call through
    (`from app.services import stripe_billing; stripe_billing.is_enabled()`),
    so no env or network is involved."""
    monkeypatch.setattr(stripe_billing, "is_enabled", lambda: True)

    def _fake_create(*, subscription, studio, success_url, cancel_url):
        return _FakeCheckoutSession(
            id=f"cs_test_{uuid.uuid4().hex[:8]}",
            url="https://checkout.stripe.test/pay/cs_test_billing",
        )

    monkeypatch.setattr(stripe_billing, "create_subscription_checkout", _fake_create)
    return monkeypatch


@pytest.fixture
def billing_off(monkeypatch):
    """Genuinely off: clear the env so the REAL `is_enabled()` computes False
    (exercises the actual gate, not a stub)."""
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    return monkeypatch


# ─── feature OFF ────────────────────────────────────────────────────────────

def test_config_reports_disabled_when_unconfigured(client, billing_off):
    r = client.get("/api/admin/billing/config")
    assert r.status_code == 200, r.text
    assert r.json() == {"enabled": False}


def test_checkout_session_returns_409_when_billing_disabled(client, auth_headers, db, billing_off):
    studio = _studio(db, "BillOff")
    r = client.post(
        f"/api/admin/billing/studios/{studio.id}/checkout-session",
        headers=auth_headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "billing_disabled"


# ─── admin-only ─────────────────────────────────────────────────────────────

def test_non_admin_instructor_forbidden_on_every_billing_route(client, db, billing_on):
    studio = _studio(db, "BillNonAdmin")
    headers = _login(client, _instructor(db, "plain-instructor"))

    r = client.get("/api/admin/billing/studios", headers=headers)
    assert r.status_code == 403, r.text

    r = client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=headers, json={"amount_cents": 10000, "currency": "usd"},
    )
    assert r.status_code == 403, r.text

    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 403, r.text


def test_non_admin_franchise_manager_forbidden_on_every_billing_route(client, db, billing_on):
    """Franchise management (level='manager' on a FranchiseOwner row) is a
    different axis than the admin role -- require_admin only ever checks
    `role == 'admin'`, so a franchise manager is still a plain 403 here."""
    studio = _studio(db, "BillFranMgr")
    headers = _login(client, _franchise_manager(db, "fran-mgr"))

    r = client.get("/api/admin/billing/studios", headers=headers)
    assert r.status_code == 403, r.text

    r = client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=headers, json={"amount_cents": 10000, "currency": "usd"},
    )
    assert r.status_code == 403, r.text

    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 403, r.text


def test_config_endpoint_needs_no_auth(client, billing_on):
    """GET /config has no Depends(require_admin) by design -- it only reveals
    the global on/off state, mirroring GET /api/payments/config."""
    r = client.get("/api/admin/billing/config")
    assert r.status_code == 200, r.text
    assert r.json() == {"enabled": True}


# ─── feature ON: roster + contracted amount + checkout ─────────────────────

def test_studios_roster_auto_creates_not_started_row(client, auth_headers, db, billing_on):
    studio = _studio(db, "BillRoster")
    r = client.get("/api/admin/billing/studios", headers=auth_headers)
    assert r.status_code == 200, r.text
    rows = {row["studio_id"]: row for row in r.json()}
    assert str(studio.id) in rows
    row = rows[str(studio.id)]
    assert row["status"] == "not_started"
    assert row["contracted_amount_cents"] is None
    assert row["has_active_checkout"] is False

    # The row is now actually persisted, not synthesized per-request.
    persisted = db.query(StudioSubscription).filter(
        StudioSubscription.studio_id == studio.id
    ).first()
    assert persisted is not None
    assert persisted.status == "not_started"


def test_studios_roster_excludes_inactive_studios(client, auth_headers, db, billing_on):
    """A database can accumulate a lot of test/demo data and deactivated
    studios over time -- an unfiltered roster would be unusable. Only
    is_active=True studios belong on the billing roster; a newly created
    active studio must still show up automatically (this is a live query,
    not a curated list)."""
    active_studio = _studio(db, "BillActive")
    inactive_studio = _studio(db, "BillInactive")
    inactive_studio.is_active = False
    db.commit()

    r = client.get("/api/admin/billing/studios", headers=auth_headers)
    assert r.status_code == 200, r.text
    studio_ids = {row["studio_id"] for row in r.json()}
    assert str(active_studio.id) in studio_ids, "a newly created active studio must appear automatically"
    assert str(inactive_studio.id) not in studio_ids, "an inactive studio must not clutter the billing roster"


def test_set_contracted_amount(client, auth_headers, db, billing_on):
    studio = _studio(db, "BillPrice")
    r = client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers,
        json={"amount_cents": 25000, "currency": "usd"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["contracted_amount_cents"] == 25000
    assert body["currency"] == "usd"

    row = db.query(StudioSubscription).filter(StudioSubscription.studio_id == studio.id).first()
    assert row is not None
    assert row.contracted_amount_cents == 25000


def test_checkout_session_with_contracted_amount_returns_checkout_url(client, auth_headers, db, billing_on):
    studio = _studio(db, "BillCheckout")
    r = client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers,
        json={"amount_cents": 30000, "currency": "usd"},
    )
    assert r.status_code == 200, r.text

    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout_url"] == "https://checkout.stripe.test/pay/cs_test_billing"
    # No contact email on this studio -> nothing emailed, but the field is present.
    assert body["emailed_to"] is None

    row = db.query(StudioSubscription).filter(StudioSubscription.studio_id == studio.id).first()
    assert row.stripe_checkout_session_id is not None


def test_checkout_session_without_contracted_amount_is_422(client, auth_headers, db, billing_on):
    studio = _studio(db, "BillNoPrice")
    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=auth_headers)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "no_contracted_amount"


# ─── the roster reflects a studio's manually-assigned pricing tier ────────
# (Studio.pricing_tier_id, set through PUT /api/studios/{id} — see
# test_pricing_tiers.py and test_studio_pricing_tier_email.py for the
# assignment path itself. This file only checks the billing roster reads it.)

def test_roster_no_tier_when_none_assigned(client, auth_headers, db, billing_on):
    studio = _studio(db, "BillNoTier")
    r = client.get("/api/admin/billing/studios", headers=auth_headers)
    row = {x["studio_id"]: x for x in r.json()}[str(studio.id)]
    assert row["tier_name"] is None
    assert row["tier_amount_cents"] is None


def test_roster_shows_the_studios_assigned_tier(client, auth_headers, db, billing_on):
    tier = _tier(db, "BillTier", cents=8000)
    studio = _studio(db, "BillWithTier")
    studio.pricing_tier_id = tier.id
    db.commit()

    r = client.get("/api/admin/billing/studios", headers=auth_headers)
    row = {x["studio_id"]: x for x in r.json()}[str(studio.id)]
    assert row["tier_name"] == tier.name
    assert row["tier_amount_cents"] == 8000


def test_set_contracted_amount_returns_full_row_shape(client, auth_headers, db, billing_on):
    """Regression: the single-row update must return the SAME shape as the
    roster (tier fields present), or the UI blanks the pills on save."""
    studio = _studio(db, "BillFullRow")
    r = client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 8000, "currency": "usd"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tier_name" in body and "tier_amount_cents" in body


# ─── "Send Checkout Link" emails the studio contact ────────────────────────

def test_checkout_emails_studio_contact_with_link(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillEmailLink")
    studio.contact_email = "owner@billemaillink.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 5900, "currency": "usd"},
    )
    sent = []
    monkeypatch.setattr(
        email_module, "send_billing_checkout_email",
        lambda to, sn, tn, cost, url: sent.append((to, url)) or "subj",
    )
    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["emailed_to"] == "owner@billemaillink.test"
    assert body["checkout_url"]
    assert len(sent) == 1 and sent[0][0] == "owner@billemaillink.test"


def test_checkout_without_contact_email_still_returns_link(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillEmailNone")   # no contact_email
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 5900, "currency": "usd"},
    )
    sent = []
    monkeypatch.setattr(email_module, "send_billing_checkout_email", lambda *a, **k: sent.append(a) or "subj")
    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["emailed_to"] is None
    assert r.json()["checkout_url"]
    assert sent == [], "no send should be attempted without a contact email"


def test_checkout_email_failure_does_not_fail_checkout(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillEmailBoom")
    studio.contact_email = "owner@billemailboom.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 5900, "currency": "usd"},
    )
    def _boom(*a, **k):
        raise RuntimeError("SMTP is down")
    monkeypatch.setattr(email_module, "send_billing_checkout_email", _boom)
    r = client.post(f"/api/admin/billing/studios/{studio.id}/checkout-session", headers=auth_headers)
    assert r.status_code == 200, r.text  # checkout still succeeds
    assert r.json()["emailed_to"] is None  # send failed -> None, not a 500
    assert r.json()["checkout_url"]


# ─── webhook ────────────────────────────────────────────────────────────────

def _row_for(db, studio):
    return db.query(StudioSubscription).filter(StudioSubscription.studio_id == studio.id).first()


def test_webhook_checkout_completed_sets_active_and_stores_ids(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillWebhook")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)
    assert row.status == "not_started"

    event = _checkout_completed_event(
        event_id="evt_bill_1", studio_subscription_id=row.id,
        stripe_subscription_id="sub_abc", stripe_customer_id="cus_abc",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)

    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "active"
    assert row.stripe_subscription_id == "sub_abc"
    assert row.stripe_customer_id == "cus_abc"
    assert row.last_webhook_event_id == "evt_bill_1"


def test_webhook_subscription_updated_active_sets_status_and_period_end(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillWebhook2")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    period_end = datetime.utcnow() + timedelta(days=30)
    event = _subscription_event(
        event_id="evt_bill_2", event_type="customer.subscription.updated", status="active",
        studio_subscription_id=row.id, stripe_subscription_id="sub_xyz",
        stripe_customer_id="cus_xyz", current_period_end=period_end,
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)

    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "active"
    assert row.stripe_subscription_id == "sub_xyz"
    assert row.current_period_end is not None
    # Truncate to the second: Stripe timestamps are integer seconds.
    assert abs((row.current_period_end - period_end).total_seconds()) < 1


def test_webhook_reads_period_end_from_subscription_items_on_new_api_versions(client, auth_headers, db, billing_on, monkeypatch):
    """Real-world shape: a live event can carry `current_period_end` only on
    the subscription item, so the row's next-payment date stayed NULL until
    this fallback existed."""
    studio = _studio(db, "BillWebhookItemPeriod")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 5900, "currency": "usd"},
    )
    row = _row_for(db, studio)

    period_end = datetime.utcnow() + timedelta(days=30)
    event = _subscription_event_with_item_period_end(
        item_current_period_end=period_end,
        event_id="evt_bill_item_pe", event_type="customer.subscription.updated",
        status="active", studio_subscription_id=row.id,
        stripe_subscription_id="sub_item_pe", stripe_customer_id="cus_item_pe",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)

    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "active"
    assert row.current_period_end is not None
    assert abs((row.current_period_end - period_end).total_seconds()) < 1


def test_webhook_redelivery_of_same_event_id_is_a_no_op(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillWebhookIdem")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    event = _checkout_completed_event(
        event_id="evt_bill_idem", studio_subscription_id=row.id,
        stripe_subscription_id="sub_idem", stripe_customer_id="cus_idem",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)

    r1 = client.post("/api/webhooks/stripe/billing", content=b"{}",
                     headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r1.status_code == 200, r1.text
    db.refresh(row)
    assert row.status == "active"
    assert row.last_webhook_event_id == "evt_bill_idem"
    updated_at_after_first = row.updated_at

    # Redeliver the SAME event id -- a genuinely different second delivery
    # (a second row-touching call), but the webhook must recognize it as
    # already-applied and no-op before deriving/writing anything again.
    r2 = client.post("/api/webhooks/stripe/billing", content=b"{}",
                     headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r2.status_code == 200, r2.text

    db.refresh(row)
    assert row.status == "active"
    assert row.last_webhook_event_id == "evt_bill_idem", "redelivery must not process again"
    assert row.stripe_subscription_id == "sub_idem"
    assert row.updated_at == updated_at_after_first, "a no-op redelivery must not touch the row at all"


def test_webhook_subscription_deleted_sets_canceled(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillWebhookCancel")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    # First get it to active via checkout.session.completed.
    active_event = _checkout_completed_event(
        event_id="evt_bill_active", studio_subscription_id=row.id,
        stripe_subscription_id="sub_cancel_me", stripe_customer_id="cus_cancel_me",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: active_event)
    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text
    db.refresh(row)
    assert row.status == "active"

    deleted_event = _deleted_event(
        event_id="evt_bill_deleted", studio_subscription_id=row.id,
        stripe_subscription_id="sub_cancel_me",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: deleted_event)
    r2 = client.post("/api/webhooks/stripe/billing", content=b"{}",
                     headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r2.status_code == 200, r2.text

    db.refresh(row)
    assert row.status == "canceled"
    assert row.last_webhook_event_id == "evt_bill_deleted"


def test_webhook_falls_back_to_stripe_subscription_id_when_metadata_missing(
    client, auth_headers, db, billing_on, monkeypatch
):
    """Belt-and-suspenders coverage: `subscription_data.metadata` at Checkout
    creation should make every later event carry `studio_subscription_id`
    directly, but this proves the row is STILL resolvable even if a real
    Stripe event ever arrives with no metadata at all (e.g. a subscription
    touched from the Stripe dashboard) -- via `obj.id`/`obj.subscription`
    matched against the row's already-stored `stripe_subscription_id`."""
    studio = _studio(db, "BillWebhookFallback")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    # First event (normal path, WITH metadata) activates the row and stamps
    # stripe_subscription_id -- this is what the fallback will match against.
    active_event = _checkout_completed_event(
        event_id="evt_bill_fb_1", studio_subscription_id=row.id,
        stripe_subscription_id="sub_fallback_target", stripe_customer_id="cus_fallback",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: active_event)
    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text
    db.refresh(row)
    assert row.status == "active"
    assert row.stripe_subscription_id == "sub_fallback_target"

    # Second event: customer.subscription.updated with EMPTY metadata (as if
    # it never propagated), but obj.id equals the already-stored
    # stripe_subscription_id -- must resolve via the fallback, not metadata.
    no_metadata_event = {
        "id": "evt_bill_fb_2",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_fallback_target",
                "status": "active",
                "customer": "cus_fallback",
                "metadata": {},
            }
        },
    }
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: no_metadata_event)
    r2 = client.post("/api/webhooks/stripe/billing", content=b"{}",
                     headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r2.status_code == 200, r2.text

    db.refresh(row)
    assert row.status == "active"
    assert row.last_webhook_event_id == "evt_bill_fb_2"


# ─── payment-issue notification email ───────────────────────────────────────

def test_webhook_past_due_transition_sends_notification_email(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillPastDueNotify")
    studio.contact_email = "owner@billpastduenotify.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    sent = []
    monkeypatch.setattr(
        email_module, "send_billing_payment_issue_email",
        lambda to, name, status: sent.append((to, name, status)) or "subject",
    )

    event = _subscription_event(
        event_id="evt_bill_pastdue", event_type="customer.subscription.updated",
        status="past_due", studio_subscription_id=row.id,
        stripe_subscription_id="sub_pd", stripe_customer_id="cus_pd",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)
    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "past_due"
    assert sent == [("owner@billpastduenotify.test", studio.display_name or studio.name, "past_due")]


def test_webhook_canceled_transition_sends_notification_email(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillCanceledNotify")
    studio.contact_email = "owner@billcanceled.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    sent = []
    monkeypatch.setattr(
        email_module, "send_billing_payment_issue_email",
        lambda to, name, status: sent.append((to, name, status)) or "subject",
    )

    deleted_event = _deleted_event(
        event_id="evt_bill_cancel_notify", studio_subscription_id=row.id,
        stripe_subscription_id="sub_cancel_notify",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: deleted_event)
    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "canceled"
    assert sent == [("owner@billcanceled.test", studio.display_name or studio.name, "canceled")]


def test_webhook_active_transition_does_not_send_payment_issue_email(client, auth_headers, db, billing_on, monkeypatch):
    """The email is only for past_due/canceled -- an ordinary activation must
    never trigger it."""
    studio = _studio(db, "BillActiveNoNotify")
    studio.contact_email = "owner@billactivenonotify.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    sent = []
    monkeypatch.setattr(
        email_module, "send_billing_payment_issue_email",
        lambda to, name, status: sent.append((to, name, status)) or "subject",
    )

    event = _checkout_completed_event(
        event_id="evt_bill_active_notify", studio_subscription_id=row.id,
        stripe_subscription_id="sub_active_notify", stripe_customer_id="cus_active_notify",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)
    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "active"
    assert sent == []


def test_webhook_redelivery_does_not_resend_notification_email(client, auth_headers, db, billing_on, monkeypatch):
    """Idempotency guards the whole handler before the status transition is
    even computed, so a redelivered event must not re-send the email either."""
    studio = _studio(db, "BillPastDueRedeliverNotify")
    studio.contact_email = "owner@billpastdueredeliver.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    sent = []
    monkeypatch.setattr(
        email_module, "send_billing_payment_issue_email",
        lambda to, name, status: sent.append((to, name, status)) or "subject",
    )

    event = _subscription_event(
        event_id="evt_bill_pd_redeliver", event_type="customer.subscription.updated",
        status="past_due", studio_subscription_id=row.id,
        stripe_subscription_id="sub_pd_redeliver", stripe_customer_id="cus_pd_redeliver",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)

    r1 = client.post("/api/webhooks/stripe/billing", content=b"{}",
                     headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/webhooks/stripe/billing", content=b"{}",
                     headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r2.status_code == 200, r2.text

    assert len(sent) == 1, "a redelivered event must not send a second email"


def test_webhook_notification_email_failure_does_not_fail_the_webhook(client, auth_headers, db, billing_on, monkeypatch):
    """A send failure must never turn a 200 ack into an error -- Stripe would
    just retry the same event, and idempotency would then no-op it anyway."""
    studio = _studio(db, "BillNotifyFails")
    studio.contact_email = "owner@billnotifyfails.test"
    db.commit()
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)

    def _boom(*args, **kwargs):
        raise RuntimeError("SMTP is down")
    monkeypatch.setattr(email_module, "send_billing_payment_issue_email", _boom)

    event = _subscription_event(
        event_id="evt_bill_notify_fails", event_type="customer.subscription.updated",
        status="past_due", studio_subscription_id=row.id,
        stripe_subscription_id="sub_notify_fails", stripe_customer_id="cus_notify_fails",
    )
    monkeypatch.setattr(stripe_billing, "construct_event", lambda payload, sig: event)
    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 200, r.text

    db.refresh(row)
    assert row.status == "past_due", "the status write must succeed even if the email fails"


def test_webhook_bad_signature_is_400_and_writes_nothing(client, auth_headers, db, billing_on, monkeypatch):
    studio = _studio(db, "BillWebhookBadSig")
    client.post(
        f"/api/admin/billing/studios/{studio.id}/contracted-amount",
        headers=auth_headers, json={"amount_cents": 15000, "currency": "usd"},
    )
    row = _row_for(db, studio)
    assert row.status == "not_started"

    def _boom(payload, sig):
        raise ValueError("bad signature")

    monkeypatch.setattr(stripe_billing, "construct_event", _boom)

    r = client.post("/api/webhooks/stripe/billing", content=b"{}",
                    headers={"stripe-signature": "garbage"})
    assert r.status_code == 400, r.text

    db.refresh(row)
    assert row.status == "not_started", "an unverified webhook must write nothing"
    assert row.last_webhook_event_id is None
    assert row.stripe_subscription_id is None
