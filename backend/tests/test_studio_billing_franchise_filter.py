"""Admin billing roster filtered by franchise.

`GET /api/admin/billing/studios?franchise_id=` narrows the roster to studios
linked to that franchise via the `franchise_studios` association, read
through `app/data/franchise_studio_repo.py::FranchiseStudioRepo` — never a
raw `db.query(FranchiseStudio)` in the route (see
`test_data_layer_contract.py`). Links are created through the real
`POST /api/franchise-studios` endpoint rather than inserted directly, so
these tests exercise the same path production traffic would.

No Stripe seam is exercised here: `list_billing_studios` never calls
`stripe_billing.is_enabled()` (only the checkout-session route does), so no
`billing_on` fixture/monkeypatch is needed — mirrors `test_studios_roster_*`
in `test_studio_billing.py`.
"""
import uuid

import pytest
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_subscription import StudioSubscription
from app.models.user import User
from app.utils.password import hash_password


# ─── cleanup ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _cleanup(db):
    """Remove only what THIS test created.

    This used to be three unqualified `.delete()` calls that truncated
    `studio_subscriptions`, `franchise_studios` and `franchises` outright — so
    one test file destroyed data other files had created in the shared test
    database.

    Snapshotting ids and deleting only the new ones keeps the file's own
    isolation guarantees while leaving everyone else's rows alone. Children go
    first so the franchise delete never trips an FK.
    """
    def ids(model):
        return {row[0] for row in db.query(model.id).all()}

    before_franchises = ids(Franchise)
    before_links = ids(FranchiseStudio)
    before_subs = ids(StudioSubscription)

    yield

    db.rollback()

    def created(model, before):
        return [i for i in ids(model) if i not in before]

    new_subs = created(StudioSubscription, before_subs)
    if new_subs:
        db.query(StudioSubscription).filter(
            StudioSubscription.id.in_(new_subs)
        ).delete(synchronize_session=False)

    new_links = created(FranchiseStudio, before_links)
    if new_links:
        db.query(FranchiseStudio).filter(
            FranchiseStudio.id.in_(new_links)
        ).delete(synchronize_session=False)

    new_franchises = created(Franchise, before_franchises)
    if new_franchises:
        # Anything else pointing at a franchise this file made must go with it,
        # or the delete below fails exactly the way the old one did.
        db.query(FranchiseStudio).filter(
            FranchiseStudio.franchise_id.in_(new_franchises)
        ).delete(synchronize_session=False)
        db.query(FranchiseOwner).filter(
            FranchiseOwner.franchise_id.in_(new_franchises)
        ).delete(synchronize_session=False)
        db.query(Franchise).filter(
            Franchise.id.in_(new_franchises)
        ).delete(synchronize_session=False)

    db.commit()


# ─── world builders ──────────────────────────────────────────────────────

def _studio(db, label):
    s = Studio(name=f"{label}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _franchise(db, label):
    f = Franchise(name=f"{label}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(f); db.commit(); db.refresh(f)
    return f


def _link(http_client, headers, franchise, studio):
    """Assign `studio` to `franchise` via the real endpoint (not a direct
    model insert), so these tests exercise the same creation path production
    traffic uses."""
    r = http_client.post(
        "/api/franchise-studios",
        headers=headers,
        json={"franchise_id": str(franchise.id), "studio_id": str(studio.id)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _instructor(db, label):
    u = User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@billingfranchisefiltertests.com", name=label,
        password_hash=hash_password("password123"), role="instructor", is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _login(http_client, user):
    r = http_client.post("/api/auth/login", json={"email": user.email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ─── the filter itself ──────────────────────────────────────────────────

def test_franchise_filter_narrows_roster_to_linked_active_studios(client, auth_headers, db):
    franchise = _franchise(db, "FilterFran")
    other_franchise = _franchise(db, "OtherFran")
    linked_1 = _studio(db, "Linked1")
    linked_2 = _studio(db, "Linked2")
    unlinked = _studio(db, "Unlinked")
    other_franchise_studio = _studio(db, "OtherFranStudio")

    _link(client, auth_headers, franchise, linked_1)
    _link(client, auth_headers, franchise, linked_2)
    _link(client, auth_headers, other_franchise, other_franchise_studio)

    r = client.get(f"/api/admin/billing/studios?franchise_id={franchise.id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    studio_ids = {row["studio_id"] for row in r.json()}

    assert studio_ids == {str(linked_1.id), str(linked_2.id)}
    assert str(unlinked.id) not in studio_ids
    assert str(other_franchise_studio.id) not in studio_ids


def test_franchise_filter_omitted_returns_every_active_studio(client, auth_headers, db):
    """No franchise_id -> unchanged pre-existing behavior: every active
    studio, franchise-linked or not."""
    franchise = _franchise(db, "OmitFran")
    linked = _studio(db, "OmitLinked")
    unlinked = _studio(db, "OmitUnlinked")
    _link(client, auth_headers, franchise, linked)

    r = client.get("/api/admin/billing/studios", headers=auth_headers)
    assert r.status_code == 200, r.text
    studio_ids = {row["studio_id"] for row in r.json()}
    assert str(linked.id) in studio_ids
    assert str(unlinked.id) in studio_ids


def test_franchise_filter_unknown_franchise_id_returns_empty_roster(client, auth_headers, db):
    """No existence check on the optional filter -- an id that matches no
    franchise just yields an empty roster, not a 404, matching
    GET /api/franchise-studios?franchise_id='s convention."""
    _studio(db, "NoMatch")
    r = client.get(f"/api/admin/billing/studios?franchise_id={uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_franchise_filter_excludes_deactivated_link(client, auth_headers, db):
    """A removed (soft-deactivated) franchise_studios assignment must not
    still count -- FranchiseStudioRepo filters on is_active=True."""
    franchise = _franchise(db, "DeactFran")
    studio = _studio(db, "DeactStudio")
    assignment = _link(client, auth_headers, franchise, studio)

    remove = client.delete(f"/api/franchise-studios/{assignment['id']}", headers=auth_headers)
    assert remove.status_code == 200, remove.text

    r = client.get(f"/api/admin/billing/studios?franchise_id={franchise.id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_franchise_filter_excludes_inactive_studio_even_if_linked(client, auth_headers, db):
    """The roster's pre-existing is_active=True STUDIO filter still applies
    together with the franchise filter -- a deactivated studio must not
    reappear just because it has an active franchise link."""
    franchise = _franchise(db, "InactiveStudioFran")
    studio = _studio(db, "InactiveLinkedStudio")
    _link(client, auth_headers, franchise, studio)
    studio.is_active = False
    db.commit()

    r = client.get(f"/api/admin/billing/studios?franchise_id={franchise.id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_franchise_filter_forbidden_for_non_admin(client, db):
    """The franchise_id param does not open a side door around require_admin."""
    franchise = _franchise(db, "NonAdminFran")
    headers = _login(client, _instructor(db, "plain-instructor-franchise-filter"))
    r = client.get(f"/api/admin/billing/studios?franchise_id={franchise.id}", headers=headers)
    assert r.status_code == 403, r.text
