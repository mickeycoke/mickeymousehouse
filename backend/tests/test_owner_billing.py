"""Self-serve owner Billing tab — a studio
owner or franchise owner's OWN view of their studio(s)' subscription,
separate from the admin-only roster covered in `test_studio_billing.py`
(this file mirrors its style: Stripe is never touched, only
`app.services.stripe_billing`'s seams are monkeypatched).

Proves: OWNER level only (a studio/franchise MANAGER sees nothing here),
a franchise owner's studios are included (the deliberate, feature-specific
exception to the usual franchise/studio tier separation), cross-owner
isolation (one owner never sees another's studio), an admin gets nothing
here (they use the separate central roster instead), and every action route
403s on a studio outside the caller's ownership rather than trusting the
path parameter.
"""
import uuid

import pytest
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.studio_subscription import StudioSubscription
from app.models.user import User
from app.utils.password import hash_password

from app.services import stripe_billing


# ─── cleanup (snapshot-diff — these 4 tables are shared with many other
# test files; a blanket delete here has twice broken unrelated files
# elsewhere in this suite) ──────────────────────────────────────────────────

_CLEANUP_MODELS = (StudioSubscription, StudioOwner, FranchiseStudio, FranchiseOwner)


@pytest.fixture(autouse=True)
def _cleanup(db):
    before = {model: {row[0] for row in db.query(model.id).all()} for model in _CLEANUP_MODELS}
    yield
    db.rollback()
    for model in _CLEANUP_MODELS:
        new_ids = {row[0] for row in db.query(model.id).all()} - before[model]
        if new_ids:
            db.query(model).filter(model.id.in_(new_ids)).delete(synchronize_session=False)
    db.commit()


# ─── world builders ──────────────────────────────────────────────────────

def _studio(db, label):
    s = Studio(name=f"{label}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _user(db, label):
    u = User(email=f"{label}-{uuid.uuid4().hex[:8]}@ownerbillingtests.com", name=label,
              password_hash=hash_password("password123"), role="instructor", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _studio_owner(db, studio, *, level="owner", label="owner"):
    u = _user(db, label)
    db.add(StudioOwner(user_id=u.id, studio_id=studio.id, level=level, is_active=True))
    db.commit()
    return u


def _franchise_owner(db, studios, *, level="owner", label="franowner"):
    u = _user(db, label)
    franchise = Franchise(name=f"Fran-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(franchise); db.commit()
    db.add(FranchiseOwner(user_id=u.id, franchise_id=franchise.id, level=level, is_active=True))
    for s in studios:
        db.add(FranchiseStudio(franchise_id=franchise.id, studio_id=s.id, is_active=True))
    db.commit()
    return u


def _admin(db, label="admin"):
    u = User(email=f"{label}-{uuid.uuid4().hex[:8]}@ownerbillingtests.com", name=label,
              password_hash=hash_password("password123"), role="admin", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _login(client, user):
    r = client.post("/api/auth/login", json={"email": user.email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class _FakeCheckoutSession:
    def __init__(self, id, url):
        self.id = id
        self.url = url


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setattr(stripe_billing, "is_enabled", lambda: True)
    monkeypatch.setattr(
        stripe_billing, "create_subscription_checkout",
        lambda *, subscription, studio, success_url, cancel_url: _FakeCheckoutSession(
            id=f"cs_test_{uuid.uuid4().hex[:8]}", url="https://checkout.stripe.test/pay/cs_test_owner",
        ),
    )
    monkeypatch.setattr(
        stripe_billing, "create_billing_portal_session",
        lambda *, customer_id, return_url: _FakeCheckoutSession(
            id=f"bps_test_{uuid.uuid4().hex[:8]}", url="https://billing.stripe.test/p/session_owner",
        ),
    )
    return monkeypatch


def _set_price(db, studio, cents=15000, emailed=True):
    """Directly stamp a contracted price — an admin action in real life, but
    these tests are about the owner-facing routes, not re-testing the admin
    contracted-amount endpoint (already covered in test_studio_billing.py).
    By default also stamps checkout_link_emailed_at: amount+email is the
    visibility gate, and most tests here want a visible row. Pass
    emailed=False to test the not-yet-invited state."""
    from datetime import datetime
    row = db.query(StudioSubscription).filter(StudioSubscription.studio_id == studio.id).first()
    if row is None:
        row = StudioSubscription(studio_id=studio.id, status="not_started", currency="usd")
        db.add(row)
    row.contracted_amount_cents = cents
    row.checkout_link_emailed_at = datetime.utcnow() if emailed else None
    db.commit()
    return row


# ─── GET /api/billing/my-studios — ownership + level scoping ───────────────

def test_studio_owner_sees_own_studio(client, db, billing_on):
    studio = _studio(db, "MyStudio")
    owner = _studio_owner(db, studio, level="owner")
    _set_price(db, studio)  # visibility gate: amount + emailed
    headers = _login(client, owner)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    ids = {row["studio_id"] for row in r.json()}
    assert str(studio.id) in ids


def test_studio_manager_sees_nothing(client, db, billing_on):
    """'Owners only' -- a studio MANAGER (level='manager') gets an empty
    list, not the studio's billing."""
    studio = _studio(db, "MgrExcluded")
    manager = _studio_owner(db, studio, level="manager")
    headers = _login(client, manager)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_franchise_owner_sees_franchise_studios(client, db, billing_on):
    """The deliberate exception: a franchise OWNER sees billing for every
    studio in their franchise, even though franchise/studio are separate
    tiers everywhere else in the app."""
    s1 = _studio(db, "FranBillA")
    s2 = _studio(db, "FranBillB")
    owner = _franchise_owner(db, [s1, s2], level="owner")
    _set_price(db, s1)
    _set_price(db, s2)
    headers = _login(client, owner)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    ids = {row["studio_id"] for row in r.json()}
    assert {str(s1.id), str(s2.id)} <= ids


def test_franchise_manager_sees_nothing(client, db, billing_on):
    """Franchise-level MANAGER (level='manager') is not an owner -- gets
    nothing, same as a studio manager."""
    studio = _studio(db, "FranMgrExcluded")
    manager = _franchise_owner(db, [studio], level="manager")
    headers = _login(client, manager)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_owner_does_not_see_another_owners_studio(client, db, billing_on):
    mine = _studio(db, "MineOnly")
    theirs = _studio(db, "TheirsOnly")
    me = _studio_owner(db, mine, level="owner", label="me")
    _studio_owner(db, theirs, level="owner", label="them")
    _set_price(db, mine)
    _set_price(db, theirs)  # both invited — scoping, not the gate, hides theirs
    headers = _login(client, me)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    ids = {row["studio_id"] for row in r.json()}
    assert str(mine.id) in ids
    assert str(theirs.id) not in ids


def test_admin_gets_empty_my_studios(client, db, billing_on):
    """Admins use the separate central roster (/api/admin/billing/studios),
    not this self-serve surface -- confirms they don't accidentally see
    every studio here too."""
    _studio(db, "AdminIrrelevant")
    admin = _admin(db)
    headers = _login(client, admin)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_my_studios_reports_checkout_ready_and_status(client, db, billing_on):
    studio = _studio(db, "ReadyFlag")
    owner = _studio_owner(db, studio, level="owner")
    headers = _login(client, owner)

    # Before amount+email, the studio is NOT listed at all (previously it
    # appeared with checkout_ready=False).
    r = client.get("/api/billing/my-studios", headers=headers)
    assert all(row["studio_id"] != str(studio.id) for row in r.json())

    _set_price(db, studio)
    r2 = client.get("/api/billing/my-studios", headers=headers)
    row2 = next(row for row in r2.json() if row["studio_id"] == str(studio.id))
    assert row2["status"] == "not_started"
    assert row2["checkout_ready"] is True


# ─── The visibility gate itself ─────────────────────────────────────────────

def test_priced_but_not_emailed_stays_hidden(client, db, billing_on):
    """Amount alone is not enough — the admin must also have sent the
    checkout email ('Only show billing when they have an amount and
    I have sent email')."""
    studio = _studio(db, "PricedNotMailed")
    owner = _studio_owner(db, studio, level="owner")
    _set_price(db, studio, emailed=False)
    headers = _login(client, owner)

    r = client.get("/api/billing/my-studios", headers=headers)
    assert r.status_code == 200, r.text
    assert all(row["studio_id"] != str(studio.id) for row in r.json())


def test_live_subscription_visible_without_email_marker(client, db, billing_on):
    """Grandfather clause: a studio already subscribed (or past_due/canceled)
    must always see its own billing to manage it, even though the emailed
    marker predates this column and is NULL for it."""
    studio = _studio(db, "LiveSubNoMarker")
    owner = _studio_owner(db, studio, level="owner")
    row = _set_price(db, studio, emailed=False)
    row.status = "active"
    db.commit()
    headers = _login(client, owner)

    r = client.get("/api/billing/my-studios", headers=headers)
    ids = {r2["studio_id"] for r2 in r.json()}
    assert str(studio.id) in ids


# ─── POST checkout-session — ownership check + reuse of the admin logic ────

def test_checkout_session_forbidden_for_studio_outside_ownership(client, db, billing_on):
    mine = _studio(db, "CheckoutMine")
    theirs = _studio(db, "CheckoutTheirs")
    me = _studio_owner(db, mine, level="owner")
    _set_price(db, theirs)

    headers = _login(client, me)
    r = client.post(f"/api/billing/my-studios/{theirs.id}/checkout-session", headers=headers)
    assert r.status_code == 403, r.text


def test_checkout_session_forbidden_for_manager(client, db, billing_on):
    studio = _studio(db, "CheckoutMgr")
    manager = _studio_owner(db, studio, level="manager")
    _set_price(db, studio)

    headers = _login(client, manager)
    r = client.post(f"/api/billing/my-studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 403, r.text


def test_checkout_session_without_contracted_amount_is_422(client, db, billing_on):
    studio = _studio(db, "CheckoutNoPrice")
    owner = _studio_owner(db, studio, level="owner")
    headers = _login(client, owner)

    r = client.post(f"/api/billing/my-studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "no_contracted_amount"


def test_checkout_session_creates_session_for_owned_studio(client, db, billing_on):
    studio = _studio(db, "CheckoutOwned")
    owner = _studio_owner(db, studio, level="owner")
    _set_price(db, studio)
    headers = _login(client, owner)

    r = client.post(f"/api/billing/my-studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 200, r.text
    # Field-wise, not whole-dict: the response schema later grew `emailed_to`
    # (admin checkout-link email), which is None here (fixture studio has no
    # contact_email) and irrelevant to what this test pins.
    assert r.json()["checkout_url"] == "https://checkout.stripe.test/pay/cs_test_owner"

    row = db.query(StudioSubscription).filter(StudioSubscription.studio_id == studio.id).first()
    assert row.stripe_checkout_session_id is not None


def test_checkout_session_creates_session_for_franchise_owned_studio(client, db, billing_on):
    studio = _studio(db, "CheckoutFranOwned")
    owner = _franchise_owner(db, [studio], level="owner")
    _set_price(db, studio)
    headers = _login(client, owner)

    r = client.post(f"/api/billing/my-studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 200, r.text


def test_checkout_session_returns_409_when_billing_disabled(client, db, monkeypatch):
    studio = _studio(db, "CheckoutOff")
    owner = _studio_owner(db, studio, level="owner")
    _set_price(db, studio)
    monkeypatch.setattr(stripe_billing, "is_enabled", lambda: False)
    headers = _login(client, owner)

    r = client.post(f"/api/billing/my-studios/{studio.id}/checkout-session", headers=headers)
    assert r.status_code == 409, r.text


# ─── POST billing-portal-session — the past_due fix-payment flow ───────────

def test_billing_portal_forbidden_for_studio_outside_ownership(client, db, billing_on):
    mine = _studio(db, "PortalMine")
    theirs = _studio(db, "PortalTheirs")
    me = _studio_owner(db, mine, level="owner")

    row = _set_price(db, theirs)
    row.stripe_customer_id = "cus_theirs"
    db.commit()

    headers = _login(client, me)
    r = client.post(f"/api/billing/my-studios/{theirs.id}/billing-portal-session", headers=headers)
    assert r.status_code == 403, r.text


def test_billing_portal_requires_existing_stripe_customer(client, db, billing_on):
    studio = _studio(db, "PortalNoCustomer")
    owner = _studio_owner(db, studio, level="owner")
    headers = _login(client, owner)

    r = client.post(f"/api/billing/my-studios/{studio.id}/billing-portal-session", headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "no_stripe_customer"


def test_billing_portal_creates_session_when_customer_exists(client, db, billing_on):
    studio = _studio(db, "PortalReady")
    owner = _studio_owner(db, studio, level="owner")
    row = _set_price(db, studio)
    row.stripe_customer_id = "cus_ready"
    row.status = "past_due"
    db.commit()

    headers = _login(client, owner)
    r = client.post(f"/api/billing/my-studios/{studio.id}/billing-portal-session", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"] == "https://billing.stripe.test/p/session_owner"
