"""POST /api/auth/setup-link — a set-password link handed over, not emailed.

Outbound email is a single point of failure for the ONLY self-service way
back into an account: if the mail host began rejecting the app's credential,
`/auth/forgot-password` and `/auth/invite` would both go dark and there would
be no way to get anyone a password without a server shell. This endpoint
returns the link instead of sending it.

The security question these tests exist to pin: returning a magic link in
production is safe ONLY because its authorisation gate is the same one that
already lets the caller set that user's password outright via
`PUT /api/users/{id}`. If the gate ever loosens relative to that, the link
starts granting power its holder did not have, and these tests should fail.
"""
import uuid

from app.models.studio import Studio
from app.models.user import User
from app.utils.password import hash_password


def _user(db, *, email, name="Someone", role="instructor", studio_id=None, active=True):
    u = User(email=email, name=name, role=role, studio_id=studio_id,
             password_hash=hash_password("original-password"), is_active=active)
    db.add(u)
    db.flush()
    return u


def _studio(db, name):
    s = Studio(name=name)
    db.add(s)
    db.flush()
    return s


def _token_from(link):
    assert "set-password?token=" in link, link
    return link.split("token=", 1)[1]


def test_the_link_is_returned_and_no_email_is_sent(client, db, auth_headers, monkeypatch):
    """The whole point: a working link comes back on the response, and the
    email service is never touched — so a dead mail host cannot break it."""
    sent = []
    monkeypatch.setattr(
        "app.services.email.send_invite_email",
        lambda *a, **k: sent.append(a) or "should-not-be-called",
    )
    target = _user(db, email="handover@example.com", name="Hand Over")
    db.commit()

    res = client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                      headers=auth_headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "Hand Over"
    assert body["email"] == "handover@example.com"
    assert body["expires_in_hours"] > 0
    assert "set-password?token=" in body["link"]
    assert sent == [], "setup-link must not send email — that is the failure it routes around"


def test_the_link_actually_sets_a_password_and_then_dies(client, db, auth_headers):
    """End to end through the user's half of the flow, including single use.
    A hand-over link that outlived its use would be a standing back door."""
    target = _user(db, email="usesthelink@example.com", name="Uses The Link")
    db.commit()

    link = client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                       headers=auth_headers).json()["link"]
    token = _token_from(link)

    assert client.get(f"/api/auth/invite/{token}").status_code == 200

    chosen = "TheyChoseThis1!"
    assert client.post("/api/auth/set-password",
                       json={"token": token, "password": chosen}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"email": "usesthelink@example.com",
                             "password": chosen}).status_code == 200

    # Consumed. `password_set_at` now postdates the token's iat.
    reused = client.post("/api/auth/set-password",
                         json={"token": token, "password": "Attacker9!"})
    assert reused.status_code == 400


def test_a_second_link_supersedes_the_first(client, db, auth_headers):
    """Issuing a fresh link must not leave the previous one live — otherwise
    every link ever handed out stays valid for its full 72 hours."""
    target = _user(db, email="twolinks@example.com")
    db.commit()

    first = _token_from(client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                                    headers=auth_headers).json()["link"])
    second = _token_from(client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                                     headers=auth_headers).json()["link"])

    assert client.post("/api/auth/set-password",
                       json={"token": second, "password": "SecondWins1!"}).status_code == 200
    # The first is now older than password_set_at, so it is dead.
    assert client.post("/api/auth/set-password",
                       json={"token": first, "password": "FirstLoses1!"}).status_code == 400


def test_a_user_with_no_email_is_refused_with_a_reason(client, db, auth_headers):
    """Sign-in is by email + password, so a password this user set would be
    unusable. Say so instead of handing over a link that leads nowhere."""
    target = _user(db, email=None, name="Pin Only")
    db.commit()

    res = client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                      headers=auth_headers)

    assert res.status_code == 400
    assert "no email" in res.json()["detail"].lower()
    assert "pin" in res.json()["detail"].lower(), "should point at the PIN route instead"


def test_an_inactive_user_is_404(client, db, auth_headers):
    target = _user(db, email="removed@example.com", active=False)
    db.commit()
    res = client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                      headers=auth_headers)
    assert res.status_code == 404


def test_an_unknown_user_is_404(client, auth_headers):
    res = client.post("/api/auth/setup-link", json={"user_id": str(uuid.uuid4())},
                      headers=auth_headers)
    assert res.status_code == 404


def test_a_plain_instructor_cannot_issue_a_link_for_anyone(client, db):
    """THE gate. An ordinary login must not be able to mint a password link for
    a colleague — that would be account takeover from inside the building."""
    studio = _studio(db, "Setup Link Studio")
    plain = _user(db, email="plain@example.com", name="Plain", studio_id=studio.id)
    victim = _user(db, email="victim@example.com", name="Victim", studio_id=studio.id)
    db.commit()

    login = client.post("/api/auth/login",
                        json={"email": "plain@example.com", "password": "original-password"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    res = client.post("/api/auth/setup-link", json={"user_id": str(victim.id)}, headers=headers)
    assert res.status_code == 403


def test_it_is_recorded_in_the_login_log(client, db, auth_headers):
    """A password link handed out off-channel needs a trail — and the trail must
    NOT contain the token, or the audit table becomes a credential store."""
    from app.models.login_event import LoginEvent

    target = _user(db, email="audited@example.com", name="Audited")
    db.commit()

    link = client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                       headers=auth_headers).json()["link"]
    token = _token_from(link)

    rows = (db.query(LoginEvent)
            .filter(LoginEvent.event_type == "setup_link_issued",
                    LoginEvent.email_attempted == "audited@example.com")
            .all())
    assert len(rows) == 1
    row = rows[0]
    assert row.success is True
    assert row.user_id == target.id
    assert row.actor_user_id is not None, "the trail must name who issued it"
    for field in (row.detail or "", row.email_attempted or "", row.user_agent or ""):
        assert token not in field, "the token must never be persisted"


def test_issuing_a_link_marks_the_user_invited(client, db, auth_headers):
    """The owners screens read `invited` off invite_sent_at. Someone handed a
    working link HAS been invited; leaving it null would report otherwise."""
    target = _user(db, email="stamped@example.com")
    db.commit()
    assert target.invite_sent_at is None

    client.post("/api/auth/setup-link", json={"user_id": str(target.id)}, headers=auth_headers)

    db.refresh(target)
    assert target.invite_sent_at is not None


# ── THE INVARIANT ──────────────────────────────────────────────────────────
#
# The endpoint's whole safety argument is that it grants nothing a caller could
# not already do via `PUT /api/users/{id}`. That was PROSE, and it was FALSE:
# `_may_manage_user` (used by /auth/invite) also admits franchise owners and
# franchise managers and applies no target-role check, while PUT 403s them —
# so a franchise owner could mint a link for studio staff, set the password,
# and sign in as them. Every studio-scoping control in the app is bypassed by
# holding a credential rather than defeating a filter.
#
# These tests assert the invariant DIRECTLY rather than restating it, by
# issuing both requests as the same actor and comparing outcomes. If the two
# gates are ever allowed to drift apart again, this fails.
from uuid import uuid4

from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio_owner import StudioOwner


def _franchise(db, label):
    f = Franchise(name=f"{label} {uuid4().hex[:6]}", is_active=True)
    db.add(f)
    db.flush()
    return f


def _login(client, email, password="password123"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _franchise_person(db, client, franchise, level):
    email = f"{level}-{uuid4().hex[:8]}@example.com"
    u = User(email=email, name=f"{level} person", password_hash=hash_password("password123"),
             role="member", is_active=True)
    db.add(u)
    db.flush()
    db.add(FranchiseOwner(user_id=u.id, franchise_id=franchise.id, level=level, is_active=True))
    db.flush()
    return u, _login(client, email)


def _assert_no_more_power_than_put(client, headers, target):
    """setup-link must never succeed where PUT /api/users/{id} would refuse."""
    link = client.post("/api/auth/setup-link", json={"user_id": str(target.id)},
                       headers=headers)
    put = client.put(f"/api/users/{target.id}", json={"name": target.name},
                     headers=headers)
    assert not (link.status_code == 200 and put.status_code != 200), (
        f"setup-link returned {link.status_code} while PUT returned "
        f"{put.status_code} — the link grants power the caller does not have"
    )
    return link, put


def test_a_franchise_owner_cannot_mint_a_link_for_studio_staff(client, db):
    """The escalation this endpoint shipped with, before QA caught it."""
    f = _franchise(db, "Esc")
    _, headers = _franchise_person(db, client, f, "owner")
    studio = _studio(db, "Franchise Studio")
    db.add(FranchiseStudio(studio_id=studio.id, franchise_id=f.id, is_active=True))
    victim = _user(db, email=f"victim-{uuid4().hex[:8]}@example.com", studio_id=studio.id)
    db.commit()

    link, put = _assert_no_more_power_than_put(client, headers, victim)
    assert link.status_code == 403
    assert put.status_code == 403


def test_a_franchise_manager_cannot_mint_a_link_for_studio_staff(client, db):
    f = _franchise(db, "Mgr")
    _, headers = _franchise_person(db, client, f, "manager")
    studio = _studio(db, "Managed Studio")
    db.add(FranchiseStudio(studio_id=studio.id, franchise_id=f.id, is_active=True))
    victim = _user(db, email=f"victim2-{uuid4().hex[:8]}@example.com", studio_id=studio.id)
    db.commit()

    link, put = _assert_no_more_power_than_put(client, headers, victim)
    assert link.status_code == 403


def test_a_studio_owner_cannot_mint_a_link_for_an_admin_in_their_studio(client, db):
    """The target-role hole: `_may_manage_user` has no role check, so a studio
    owner could have minted a link for an ADMIN sitting in their own studio and
    escalated straight past every studio boundary."""
    studio = _studio(db, "Owner Escalation")
    owner = _user(db, email=f"owner-{uuid4().hex[:8]}@example.com",
                  role="member", studio_id=studio.id)
    db.add(StudioOwner(user_id=owner.id, studio_id=studio.id, level="owner", is_active=True))
    admin_target = _user(db, email=f"adm-{uuid4().hex[:8]}@example.com",
                         role="admin", studio_id=studio.id)
    db.commit()
    headers = _login(client, owner.email, "original-password")

    link, put = _assert_no_more_power_than_put(client, headers, admin_target)
    assert link.status_code == 403


def test_a_studio_owner_may_still_mint_for_their_own_instructor(client, db):
    """The guard must not break the case the feature exists for."""
    studio = _studio(db, "Legit Owner")
    owner = _user(db, email=f"owner2-{uuid4().hex[:8]}@example.com",
                  role="member", studio_id=studio.id)
    db.add(StudioOwner(user_id=owner.id, studio_id=studio.id, level="owner", is_active=True))
    mine = _user(db, email=f"mine-{uuid4().hex[:8]}@example.com",
                 role="instructor", studio_id=studio.id)
    db.commit()
    headers = _login(client, owner.email, "original-password")

    res = client.post("/api/auth/setup-link", json={"user_id": str(mine.id)}, headers=headers)
    assert res.status_code == 200, res.text
    assert "set-password?token=" in res.json()["link"]
