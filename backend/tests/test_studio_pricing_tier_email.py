"""Studio<->pricing-tier assignment + change email.

Product rule: each studio has a payment tier assigned to it, an admin can
manually assign payment tiers at any time, and the studio owner is emailed
when a payment tier is changed. Manual assignment only, via the existing
generic `PUT /api/studios/{id}` route (`studios.pricing_tier_id`, a nullable
FK to `pricing_tiers`).

Does NOT test actual billing (`StudioSubscription.contracted_amount_cents`)
— deliberately untouched by this feature, see app/models/studio.py's
`pricing_tier_id` column comment.

Assertion pattern: monkeypatch `app.services.email.send_pricing_tier_changed_email`
and capture its call args, same convention as
tests/test_password_reset.py::test_forgot_password_sends_email_via_background_task_for_matched_user
and tests/test_setup_link.py — no real SMTP server, `EMAIL_BACKEND` stays
irrelevant to these tests since send_email() itself is never reached.
"""
import uuid

import pytest
from app.models.pricing_tier import PricingTier
from app.models.studio import Studio


# ─── cleanup ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _cleanup(db):
    yield
    db.rollback()


# ─── world builders ─────────────────────────────────────────────────────────

def _studio(db, **overrides):
    defaults = dict(
        name=f"TierEmailStudio-{uuid.uuid4().hex[:8]}",
        contact_email="owner@example.com",
        is_active=True,
    )
    defaults.update(overrides)
    studio = Studio(**defaults)
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


def _tier(db, name, **overrides):
    defaults = dict(
        name=name,
        min_clients=1,
        max_clients=100,
        monthly_price_cents=8000,
        display_order=500,
        is_active=True,
    )
    defaults.update(overrides)
    tier = PricingTier(**defaults)
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier


def _capture_sent_emails(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.email.send_pricing_tier_changed_email",
        lambda to, studio_name, old_tier_name, new_tier_name, new_price_display: (
            calls.append(
                dict(
                    to=to,
                    studio_name=studio_name,
                    old_tier_name=old_tier_name,
                    new_tier_name=new_tier_name,
                    new_price_display=new_price_display,
                )
            )
        ),
    )
    return calls


# ─── first-time assignment ──────────────────────────────────────────────────

def test_first_time_assignment_sends_exactly_one_email(client, db, auth_headers, monkeypatch):
    studio = _studio(db, contact_email="first-assign@example.com")
    tier = _tier(db, "Studio", monthly_price_cents=8000)
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": str(tier.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pricing_tier_id"] == str(tier.id)

    assert len(calls) == 1
    sent = calls[0]
    assert sent["to"] == "first-assign@example.com"
    assert sent["old_tier_name"] == "no tier"
    assert sent["new_tier_name"] == "Studio"
    assert sent["new_price_display"] == "$80.00"

    db.refresh(studio)
    assert studio.pricing_tier_id == tier.id


# ─── tier -> different tier ─────────────────────────────────────────────────

def test_changing_from_one_tier_to_another_sends_email_with_both_names(
    client, db, auth_headers, monkeypatch,
):
    old_tier = _tier(db, "Essential", monthly_price_cents=4000, display_order=501)
    new_tier = _tier(db, "Growth", monthly_price_cents=13300, display_order=502)
    studio = _studio(db, contact_email="swap@example.com", pricing_tier_id=old_tier.id)
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": str(new_tier.id)},
    )
    assert r.status_code == 200, r.text

    assert len(calls) == 1
    sent = calls[0]
    assert sent["old_tier_name"] == "Essential"
    assert sent["new_tier_name"] == "Growth"
    assert sent["new_price_display"] == "$133.00"


# ─── same tier re-saved: no email ───────────────────────────────────────────

def test_setting_the_same_tier_again_does_not_send_a_second_email(
    client, db, auth_headers, monkeypatch,
):
    tier = _tier(db, "Scale", monthly_price_cents=20000, display_order=503)
    studio = _studio(db, contact_email="same-tier@example.com", pricing_tier_id=tier.id)
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": str(tier.id)},
    )
    assert r.status_code == 200, r.text

    assert len(calls) == 0


# ─── clearing the assignment ────────────────────────────────────────────────

def test_clearing_the_assignment_sends_an_email(client, db, auth_headers, monkeypatch):
    tier = _tier(db, "Elite", monthly_price_cents=40000, display_order=504)
    studio = _studio(db, contact_email="clear@example.com", pricing_tier_id=tier.id)
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pricing_tier_id"] is None

    assert len(calls) == 1
    sent = calls[0]
    assert sent["old_tier_name"] == "Elite"
    assert sent["new_tier_name"] == "no tier"
    assert sent["new_price_display"] == "no tier"

    db.refresh(studio)
    assert studio.pricing_tier_id is None


# ─── enterprise-style tier: custom price display ────────────────────────────

def test_assigning_a_tier_with_no_fixed_price_shows_custom(client, db, auth_headers, monkeypatch):
    tier = _tier(db, "Enterprise", min_clients=301, max_clients=None,
                  monthly_price_cents=None, display_order=505)
    studio = _studio(db, contact_email="custom-price@example.com")
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": str(tier.id)},
    )
    assert r.status_code == 200, r.text

    assert len(calls) == 1
    assert calls[0]["new_price_display"] == "custom"


# ─── no contact_email: skip, don't crash ────────────────────────────────────

def test_studio_with_no_contact_email_does_not_crash_and_does_not_send(
    client, db, auth_headers, monkeypatch,
):
    tier = _tier(db, "Studio2", monthly_price_cents=8000, display_order=506)
    studio = _studio(db, contact_email=None)
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": str(tier.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pricing_tier_id"] == str(tier.id)

    assert len(calls) == 0

    db.refresh(studio)
    assert studio.pricing_tier_id == tier.id


# ─── unrelated field update: no email ───────────────────────────────────────

def test_updating_an_unrelated_field_without_touching_tier_does_not_send_email(
    client, db, auth_headers, monkeypatch,
):
    tier = _tier(db, "Growth2", monthly_price_cents=13300, display_order=507)
    studio = _studio(db, contact_email="unrelated@example.com", pricing_tier_id=tier.id)
    calls = _capture_sent_emails(monkeypatch)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"name": "Renamed Studio Only"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Studio Only"
    # pricing_tier_id untouched
    assert r.json()["pricing_tier_id"] == str(tier.id)

    assert len(calls) == 0


# ─── send failure must not fail the save ────────────────────────────────────

def test_email_send_failure_does_not_fail_the_save(client, db, auth_headers, monkeypatch):
    tier = _tier(db, "Studio3", monthly_price_cents=8000, display_order=508)
    studio = _studio(db, contact_email="flaky@example.com")

    def _boom(*args, **kwargs):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr("app.services.email.send_pricing_tier_changed_email", _boom)

    r = client.put(
        f"/api/studios/{studio.id}",
        headers=auth_headers,
        json={"pricing_tier_id": str(tier.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pricing_tier_id"] == str(tier.id)

    db.refresh(studio)
    assert studio.pricing_tier_id == tier.id
