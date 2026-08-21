"""Pricing tiers admin feature — a platform-wide SaaS price
book CRUD, admin-only. See app/routes/pricing_tiers.py.

NOT under test here: any wiring to StudioSubscription / per-studio billing —
this table is deliberately independent of that one (see
app/models/pricing_tier.py's scope-boundary docstring).

Unauthenticated-request status code: this repo's `get_current_user` depends
on FastAPI's `HTTPBearer()` with its default `auto_error=True`, which raises
403 ("Not authenticated"), not 401, when no Authorization header is present
at all — this is the actual, already-established behavior of every other
admin-only route in this codebase (see tests/test_reporting_permissions.py's
`test_*_no_auth_returns_403` tests and test_setup_permissions.py's
docstring: "unauthenticated requests get 403"). These endpoints reuse that
same `require_admin` dependency, so they behave identically. Tested as 403
below to match reality rather than asserted as 401 against a rule this
codebase doesn't actually implement anywhere.

The 8 real tiers are seeded by the migration
(alembic/versions/9ce1624306d8_pricing_tiers.py), but this suite's `db`
fixture (conftest.py) builds its schema straight from SQLAlchemy metadata
(`Base.metadata.create_all`), never by running `alembic upgrade` — so the
migration's seed rows do not exist in the test database. The `seeded_tiers`
fixture below inserts the same 8 rows directly (get-or-create, matching
`conftest.py`'s `admin_user` fixture idiom) so the list/spot-check tests
exercise the real production data shape without depending on Alembic.
"""
import uuid

import pytest
from app.models.pricing_tier import PricingTier
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password


# ─── cleanup ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _cleanup(db):
    yield
    db.rollback()


# ─── world builders ─────────────────────────────────────────────────────────

def _instructor(db, label, role="instructor"):
    u = User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@pricingtiertests.com",
        name=label,
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(client, user):
    r = client.post("/api/auth/login", json={"email": user.email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _extra_tier(db, **overrides):
    """A throwaway tier for create/update/delete tests, kept out of the way
    of the 8 seeded rows (display_order 900+, deleted at test end)."""
    defaults = dict(
        name=f"Test-{uuid.uuid4().hex[:6]}",
        min_clients=1000,
        max_clients=1001,
        monthly_price_cents=99900,
        display_order=900,
        is_active=True,
    )
    defaults.update(overrides)
    tier = PricingTier(**defaults)
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier


# ─── seeded data: GET returns the 8 real tiers in order ────────────────────

SEEDED_TIERS = [
    ("Free", 0, 1, 0, 1),
    ("Essential", 2, 30, 4000, 2),
    ("Studio", 31, 60, 8000, 3),
    ("Growth", 61, 100, 13300, 4),
    ("Scale", 101, 150, 20000, 5),
    ("Scale Plus", 151, 200, 26700, 6),
    ("Elite", 201, 300, 40000, 7),
    ("Enterprise", 301, None, None, 8),
]


@pytest.fixture
def seeded_tiers(db):
    """Insert the 8 real tiers directly -- see this file's module docstring
    for why the test DB doesn't already have them from the migration."""
    existing = {
        row.name
        for row in db.query(PricingTier)
        .filter(PricingTier.name.in_([t[0] for t in SEEDED_TIERS]))
        .all()
    }
    for name, min_c, max_c, price_c, order in SEEDED_TIERS:
        if name in existing:
            continue
        db.add(PricingTier(
            name=name, min_clients=min_c, max_clients=max_c,
            monthly_price_cents=price_c, display_order=order, is_active=True,
        ))
    db.commit()
    return SEEDED_TIERS


def test_list_returns_the_8_seeded_tiers_in_display_order(client, auth_headers, seeded_tiers):
    r = client.get("/api/admin/pricing-tiers", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    seeded = [row for row in body if row["name"] in {t[0] for t in SEEDED_TIERS}]
    assert len(seeded) == 8, [row["name"] for row in body]
    assert [row["display_order"] for row in seeded] == sorted(row["display_order"] for row in seeded)

    by_name = {row["name"]: row for row in seeded}
    for name, min_c, max_c, price_c, order in SEEDED_TIERS:
        row = by_name[name]
        assert row["min_clients"] == min_c, name
        assert row["max_clients"] == max_c, name
        assert row["monthly_price_cents"] == price_c, name
        assert row["display_order"] == order, name
        assert row["is_active"] is True, name
        assert "id" in row and row["id"]


def test_per_client_rate_at_cap_spot_checks(client, auth_headers, seeded_tiers):
    """Formula per the API contract: monthly_price_cents / 100 / max_clients,
    rounded to 2 decimals. Essential: 4000 cents = $40; $40 / 30 clients =
    $1.333.../client -> 1.33 (matches the pricing doc's own "$40 / 30 =
    $1.33/client" anchor). Free: price is 0, not null, and max_clients=1 is
    also not null -- under the contract's stated null condition ("null if
    max_clients is null OR monthly_price_cents is null") neither input is
    null, so this computes as a real rate, 0.0, not null. Enterprise: both
    inputs are null -> null.
    """
    r = client.get("/api/admin/pricing-tiers", headers=auth_headers)
    assert r.status_code == 200, r.text
    by_name = {row["name"]: row for row in r.json()}

    assert by_name["Free"]["per_client_rate_at_cap"] == 0.0
    assert by_name["Essential"]["per_client_rate_at_cap"] == 1.33
    assert by_name["Studio"]["per_client_rate_at_cap"] == 1.33
    assert by_name["Growth"]["per_client_rate_at_cap"] == 1.33
    assert by_name["Scale"]["per_client_rate_at_cap"] == 1.33
    assert by_name["Scale Plus"]["per_client_rate_at_cap"] == 1.33
    assert by_name["Elite"]["per_client_rate_at_cap"] == 1.33
    assert by_name["Enterprise"]["per_client_rate_at_cap"] is None


# ─── create / update / delete ───────────────────────────────────────────────

def test_create_update_delete_round_trip(client, auth_headers, db):
    create_body = {
        "name": "Pytest Tier",
        "min_clients": 500,
        "max_clients": 600,
        "monthly_price_cents": 50000,
        "display_order": 950,
    }
    r = client.post("/api/admin/pricing-tiers", headers=auth_headers, json=create_body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "Pytest Tier"
    assert created["min_clients"] == 500
    assert created["max_clients"] == 600
    assert created["monthly_price_cents"] == 50000
    assert created["display_order"] == 950
    assert created["is_active"] is True
    # 50000/100/600 = 0.8333... -> 0.83
    assert created["per_client_rate_at_cap"] == 0.83
    tier_id = created["id"]

    r = client.put(
        f"/api/admin/pricing-tiers/{tier_id}",
        headers=auth_headers,
        json={"monthly_price_cents": 60000, "name": "Pytest Tier Renamed"},
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["id"] == tier_id
    assert updated["name"] == "Pytest Tier Renamed"
    assert updated["monthly_price_cents"] == 60000
    # unspecified fields are unchanged
    assert updated["min_clients"] == 500
    assert updated["max_clients"] == 600
    # 60000/100/600 = 1.0
    assert updated["per_client_rate_at_cap"] == 1.0

    r = client.delete(f"/api/admin/pricing-tiers/{tier_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"message": "Pricing tier deactivated"}

    # Soft delete: the row still exists, is_active=False, never hard-deleted.
    row = db.query(PricingTier).filter(PricingTier.id == uuid.UUID(tier_id)).first()
    assert row is not None
    assert row.is_active is False

    # And it drops out of the active listing.
    r = client.get("/api/admin/pricing-tiers", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert tier_id not in {row["id"] for row in r.json()}


def test_create_enterprise_style_tier_nulls_round_trip(client, auth_headers):
    r = client.post(
        "/api/admin/pricing-tiers",
        headers=auth_headers,
        json={
            "name": "Pytest Enterprise",
            "min_clients": 2000,
            "max_clients": None,
            "monthly_price_cents": None,
            "display_order": 960,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["max_clients"] is None
    assert body["monthly_price_cents"] is None
    assert body["per_client_rate_at_cap"] is None


# ─── admin-only ─────────────────────────────────────────────────────────────

def test_non_admin_instructor_forbidden_on_every_route(client, db, auth_headers):
    tier = _extra_tier(db, display_order=901)
    headers = _login(client, _instructor(db, "plain-instructor"))

    r = client.get("/api/admin/pricing-tiers", headers=headers)
    assert r.status_code == 403, r.text

    r = client.post(
        "/api/admin/pricing-tiers",
        headers=headers,
        json={"name": "x", "min_clients": 1, "max_clients": 2, "monthly_price_cents": 100, "display_order": 999},
    )
    assert r.status_code == 403, r.text

    r = client.put(f"/api/admin/pricing-tiers/{tier.id}", headers=headers, json={"name": "y"})
    assert r.status_code == 403, r.text

    r = client.delete(f"/api/admin/pricing-tiers/{tier.id}", headers=headers)
    assert r.status_code == 403, r.text


def test_non_admin_manager_forbidden_on_every_route(client, db, auth_headers):
    """require_admin only ever checks `role == 'admin'` -- 'manager' is a
    real base role one rung below admin (CLAUDE.md's role hierarchy) and
    still gets a plain 403 here."""
    tier = _extra_tier(db, display_order=902)
    headers = _login(client, _instructor(db, "non-admin-manager", role="manager"))

    r = client.get("/api/admin/pricing-tiers", headers=headers)
    assert r.status_code == 403, r.text

    r = client.post(
        "/api/admin/pricing-tiers",
        headers=headers,
        json={"name": "x", "min_clients": 1, "max_clients": 2, "monthly_price_cents": 100, "display_order": 998},
    )
    assert r.status_code == 403, r.text

    r = client.put(f"/api/admin/pricing-tiers/{tier.id}", headers=headers, json={"name": "y"})
    assert r.status_code == 403, r.text

    r = client.delete(f"/api/admin/pricing-tiers/{tier.id}", headers=headers)
    assert r.status_code == 403, r.text


def test_non_admin_studio_owner_forbidden_on_every_route(client, db, auth_headers):
    """Studio ownership (a StudioOwner row) is a relationship on top of a
    base role, not the `role` column itself (CLAUDE.md: "Owners are not a
    role") -- require_admin never looks at it, so an owner with role
    'instructor' still gets a plain 403 here, same as any other
    non-admin."""
    tier = _extra_tier(db, display_order=903)
    owner_user = _instructor(db, "non-admin-owner")
    studio = Studio(name=f"PricingTierOwnerStudio-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(studio)
    db.commit()
    db.add(StudioOwner(user_id=owner_user.id, studio_id=studio.id, level="owner", is_active=True))
    db.commit()
    headers = _login(client, owner_user)

    r = client.get("/api/admin/pricing-tiers", headers=headers)
    assert r.status_code == 403, r.text

    r = client.post(
        "/api/admin/pricing-tiers",
        headers=headers,
        json={"name": "x", "min_clients": 1, "max_clients": 2, "monthly_price_cents": 100, "display_order": 996},
    )
    assert r.status_code == 403, r.text

    r = client.put(f"/api/admin/pricing-tiers/{tier.id}", headers=headers, json={"name": "y"})
    assert r.status_code == 403, r.text

    r = client.delete(f"/api/admin/pricing-tiers/{tier.id}", headers=headers)
    assert r.status_code == 403, r.text


def test_unauthenticated_request_rejected_on_every_route(client, db):
    """No Authorization header at all -- see this file's module docstring
    for why 403, not 401, is this codebase's real behavior."""
    tier = _extra_tier(db, display_order=903)

    assert client.get("/api/admin/pricing-tiers").status_code == 403

    assert client.post(
        "/api/admin/pricing-tiers",
        json={"name": "x", "min_clients": 1, "max_clients": 2, "monthly_price_cents": 100, "display_order": 997},
    ).status_code == 403

    assert client.put(f"/api/admin/pricing-tiers/{tier.id}", json={"name": "y"}).status_code == 403

    assert client.delete(f"/api/admin/pricing-tiers/{tier.id}").status_code == 403


def test_get_or_404_on_nonexistent_tier(client, auth_headers):
    r = client.put(
        f"/api/admin/pricing-tiers/{uuid.uuid4()}",
        headers=auth_headers,
        json={"name": "nope"},
    )
    assert r.status_code == 404, r.text

    r = client.delete(f"/api/admin/pricing-tiers/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404, r.text
