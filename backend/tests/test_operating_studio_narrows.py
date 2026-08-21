"""X-Studio-Id must NARROW, never GRANT.

`get_managed_studio_ids` used to `return {operating_studio_id}` for any caller,
treating the header as authoritative. For an admin that is a narrowing — they are
already entitled everywhere. For anyone else it was a grant.

The escalation, reproduced end to end by an independent verifier
against the supposedly-fixed studio_owners router: a franchise-A manager who also
holds ANY staff attachment at a studio in franchise B (an instructor membership,
a StudioOwner row, or just `user.studio_id`) is allowed to send that studio's id
by `dependencies.get_operating_studio_id`. They then read franchise B's owner
roster INCLUDING EMAILS, flipped `is_active` to lock a legitimate owner out, and
POSTed a new owner assignment — 201, an owner row at another franchise's studio.

Every case below is written against the helper AND over HTTP, because the helper
is a chokepoint for `auth.py`, `studios.py`, `users.py` and `studio_owners.py`:
a change here has to be proven not to have broken the legitimate path.
"""
from uuid import uuid4

import pytest

from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.ownership import get_managed_studio_ids
from app.utils.password import hash_password


def _studio(db, label):
    s = Studio(name=f"{label}-{uuid4().hex[:6]}", display_name=label, is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _user(db, label, role="instructor", studio_id=None):
    u = User(
        email=f"{label}-{uuid4().hex[:6]}@example.com",
        name=label,
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
        studio_id=studio_id,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _owns(db, user, studio, level="manager"):
    row = StudioOwner(user_id=user.id, studio_id=studio.id, level=level, is_active=True)
    db.add(row); db.commit(); db.refresh(row)
    return row


@pytest.fixture
def two_studios(db):
    return _studio(db, "NarrowA"), _studio(db, "NarrowB")


# ─── the escalation is closed ────────────────────────────────────────────────

def test_header_for_an_unmanaged_studio_grants_nothing(db, two_studios):
    """THE BUG. Manager of A, staff attachment at B, sends B's id."""
    a, b = two_studios
    mgr = _user(db, "mgr-a", studio_id=b.id)   # primary studio in the OTHER studio
    _owns(db, mgr, a)                          # but only manages A

    assert get_managed_studio_ids(db, mgr, operating_studio_id=b.id) == set(), (
        "naming a studio you do not manage granted management of it"
    )


def test_header_for_a_managed_studio_still_works(db, two_studios):
    """The legitimate narrowing — this is what must NOT break."""
    a, b = two_studios
    mgr = _user(db, "mgr-ab")
    _owns(db, mgr, a)
    _owns(db, mgr, b)

    assert get_managed_studio_ids(db, mgr, operating_studio_id=a.id) == {a.id}
    assert get_managed_studio_ids(db, mgr, operating_studio_id=b.id) == {b.id}


def test_no_header_returns_everything_managed(db, two_studios):
    a, b = two_studios
    mgr = _user(db, "mgr-both")
    _owns(db, mgr, a)
    _owns(db, mgr, b)
    assert get_managed_studio_ids(db, mgr) == {a.id, b.id}


def test_inactive_ownership_row_grants_nothing(db, two_studios):
    a, _ = two_studios
    mgr = _user(db, "mgr-retired")
    row = _owns(db, mgr, a)
    row.is_active = False
    db.commit()
    assert get_managed_studio_ids(db, mgr) == set()
    assert get_managed_studio_ids(db, mgr, operating_studio_id=a.id) == set()


# ─── the admin path is deliberately unchanged ────────────────────────────────

def test_admin_with_no_header_is_unrestricted(db):
    admin = _user(db, "admin-none", role="admin")
    assert get_managed_studio_ids(db, admin) is None, (
        "None means 'all studios' — an admin with no operating studio keeps it"
    )


def test_admin_with_a_header_is_narrowed_to_it(db, two_studios):
    """An admin is already entitled everywhere, so the header can only narrow —
    including to a studio the admin holds no StudioOwner row for, which is the
    normal case and why the admin branch is separate."""
    a, _ = two_studios
    admin = _user(db, "admin-scoped", role="admin")
    assert get_managed_studio_ids(db, admin, operating_studio_id=a.id) == {a.id}


# ─── over HTTP, through the router that exposed it ───────────────────────────

def test_cross_franchise_owner_roster_is_not_readable_over_http(
    client, auth_headers, db, two_studios
):
    """Admin credentials with X-Studio-Id are the only combination the existing
    isolation suite covered; this asserts the LIST cannot be widened by naming
    another studio. The list is where user_email is actually populated — the
    by-id GET leaves it null, so this is the endpoint that leaked PII."""
    a, b = two_studios
    owner_b = _user(db, "owner-b", studio_id=b.id)
    _owns(db, owner_b, b, level="owner")

    r = client.get("/api/studio-owners", headers={**auth_headers, "X-Studio-Id": str(a.id)})
    assert r.status_code == 200, r.text
    studio_ids = {row["studio_id"] for row in r.json()}
    assert str(b.id) not in studio_ids, (
        "operating in studio A returned studio B's owner assignments"
    )
    emails = {row.get("user_email") for row in r.json()}
    assert owner_b.email not in emails, "another studio's owner email was disclosed"
