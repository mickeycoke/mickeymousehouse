"""PUT /api/users/{id} must not answer a duplicate email with a raw 500.

The bug this guards against, "setting a password from the administrator does
not work": the admin edited one person, set a real email AND a new
password, and the email was already held by a second row. `update_user` had no
duplicate-email guard, so `users_email_key` fired as an unhandled 500 — and
because the password hash rides the same transaction it rolled back with the
email. Nothing was saved, and the screen said nothing useful.

What is pinned here:
  * a collision answers 400 with a readable message, never 500
  * the rejected save is ATOMIC: the old password still logs in and the email
    is unchanged (asserted through /api/auth/login, not by reading the row)
  * re-saving a row's OWN email alongside a new password still works — the edit
    form always posts the email back, so the guard must not fire on it
  * a soft-deleted holder still blocks (`create_user` revives that same row,
    so its email is not free to hand to a different one)
  * a studio owner gets the same 400, and learns the holder's NAME only when
    the holder is inside a studio they manage
"""
from uuid import uuid4

from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password

STAMP = uuid4().hex[:8]
PASSWORD = "password123"


# ── world ────────────────────────────────────────────────────────────────────

def _studio(db, label):
    s = Studio(name=f"{label} {uuid4().hex[:6]}", display_name=f"{label} {STAMP}", is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _person(db, studio, *, name=None, password=PASSWORD, role="instructor", is_active=True):
    """Stamped-unique email so the shared test DB stays clean across the run."""
    u = User(
        email=f"emailconflict-{uuid4().hex[:10]}@example.com",
        name=name or f"Person {uuid4().hex[:4]}",
        password_hash=hash_password(password),
        role=role,
        studio_id=studio.id if studio else None,
        is_active=is_active,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _owner_headers(db, client, studio):
    email = f"emailconflict-owner-{uuid4().hex[:8]}@example.com"
    owner = User(email=email, name="Studio Owner", password_hash=hash_password(PASSWORD),
                 role="instructor", studio_id=studio.id, is_active=True)
    db.add(owner)
    db.commit()
    db.add(StudioOwner(user_id=owner.id, studio_id=studio.id, level="owner", is_active=True))
    db.commit()
    return _headers(client, email, PASSWORD)


def _headers(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login for {email} failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _login_status(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).status_code


# ── the bug ──────────────────────────────────────────────────────────────────

def test_collision_with_an_active_user_is_400_not_500(client, db, auth_headers):
    studio = _studio(db, "Conflict")
    target = _person(db, studio, name="Julie Galloway")
    holder = _person(db, studio, name="Admin Row")

    resp = client.put(
        f"/api/users/{target.id}",
        json={"name": target.name, "email": holder.email, "password": "brandnewpass"},
        headers=auth_headers,
    )

    assert resp.status_code == 400, f"expected a clean 400, got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert "Admin Row" in detail, f"the message must name the account holding the email: {detail!r}"
    assert "email" in detail.lower()


def test_a_rejected_save_writes_nothing_at_all(client, db, auth_headers):
    """THE REGRESSION THAT COST THE OWNER THE PASSWORD. A refused email must not
    take the password with it — proven by logging in, not by reading the row."""
    studio = _studio(db, "Atomic")
    target = _person(db, studio, name="Target")
    holder = _person(db, studio, name="Holder")
    old_email = target.email

    resp = client.put(
        f"/api/users/{target.id}",
        json={"email": holder.email, "password": "thenewpassword"},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    assert _login_status(client, old_email, PASSWORD) == 200, \
        "the rejected save clobbered the old password"
    assert _login_status(client, old_email, "thenewpassword") == 401, \
        "the new password was written even though the save was refused"

    db.expire(target)
    db.refresh(target)
    assert target.email == old_email, "the email was partially written"
    assert holder.email != old_email


def test_resaving_your_own_email_with_a_new_password_still_works(client, db, auth_headers):
    """The edit form posts the email back on every save, so the guard must not
    fire on a no-op re-save. This is the path the owner actually needs."""
    studio = _studio(db, "NoOp")
    target = _person(db, studio, name="Unchanged")

    resp = client.put(
        f"/api/users/{target.id}",
        json={"name": "Unchanged", "email": target.email, "password": "freshpassword"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, f"a no-op email re-save was rejected: {resp.text}"
    assert resp.json()["email"] == target.email
    assert _login_status(client, target.email, "freshpassword") == 200, \
        "the new password did not take"
    assert _login_status(client, target.email, PASSWORD) == 401


def test_a_non_colliding_email_change_plus_password_still_works(client, db, auth_headers):
    studio = _studio(db, "Moved")
    target = _person(db, studio, name="Mover")
    fresh = f"emailconflict-moved-{uuid4().hex[:8]}@example.com"

    resp = client.put(
        f"/api/users/{target.id}",
        json={"email": fresh, "password": "movedpassword"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == fresh
    assert _login_status(client, fresh, "movedpassword") == 200


# ── the soft-deleted ruling ──────────────────────────────────────────────────

def test_a_soft_deleted_holder_still_blocks_the_email(client, db, auth_headers):
    """RULING: blocked, with a message that says the holder is gone.

    Delete is soft, and `create_user` REVIVES the row that owns an email rather
    than erroring — so the email is still that account's key back in. Handing it
    to a different row here would strand the removed account's sessions, so
    update refuses instead of stealing.
    """
    studio = _studio(db, "SoftDeleted")
    target = _person(db, studio, name="Target")
    gone = _person(db, studio, name="Removed Person")
    gone_email = gone.email
    assert client.delete(f"/api/users/{gone.id}", headers=auth_headers).status_code == 200

    resp = client.put(
        f"/api/users/{target.id}",
        json={"email": gone_email},
        headers=auth_headers,
    )

    assert resp.status_code == 400, f"expected the removed holder to block: {resp.text}"
    detail = resp.json()["detail"]
    assert "Removed Person" in detail and "removed account" in detail, detail

    db.expire(target)
    db.refresh(target)
    assert target.email != gone_email

    # And the create path is unchanged: re-adding that email revives the SAME
    # row, which is exactly why update may not take it.
    revived = client.post(
        "/api/users",
        json={"email": gone_email, "name": "Removed Person", "password": PASSWORD,
              "role": "instructor", "studio_id": str(studio.id)},
        headers=auth_headers,
    )
    assert revived.status_code == 201, revived.text
    assert revived.json()["id"] == str(gone.id)


# ── scoped (non-admin) callers ───────────────────────────────────────────────

def test_studio_owner_gets_the_same_400_and_sees_their_own_studio_s_name(client, db):
    studio = _studio(db, "OwnerScope")
    headers = _owner_headers(db, client, studio)
    target = _person(db, studio, name="Their Instructor")
    holder = _person(db, studio, name="Their Other Instructor")

    resp = client.put(
        f"/api/users/{target.id}",
        json={"email": holder.email, "password": "ownersetpass"},
        headers=headers,
    )

    assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
    assert "Their Other Instructor" in resp.json()["detail"]
    # atomic for a scoped caller too
    assert _login_status(client, target.email, PASSWORD) == 200


def test_studio_owner_is_not_told_the_name_of_a_holder_in_another_studio(client, db):
    """Same 400, but a name from a studio they cannot see is not disclosed —
    the same thing `create_user` says when the email is out of their scope."""
    mine = _studio(db, "MineScope")
    theirs = _studio(db, "TheirsScope")
    headers = _owner_headers(db, client, mine)
    target = _person(db, mine, name="My Instructor")
    outsider = _person(db, theirs, name="Somebody Elsewhere")

    resp = client.put(
        f"/api/users/{target.id}",
        json={"email": outsider.email},
        headers=headers,
    )

    assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert detail == "Email already registered", detail
    assert "Somebody Elsewhere" not in detail


# ── neighbouring behaviour the guard must not disturb ─────────────────────────

def test_clearing_the_email_leaves_null_and_two_blanks_do_not_collide(client, db, auth_headers):
    """A PIN-only instructor has no email. Two of them must coexist, which only
    holds while blank is NULL — '' is a real value under the unique index."""
    studio = _studio(db, "Blank")
    one = _person(db, studio, name="Blank One")
    two = _person(db, studio, name="Blank Two")

    for person in (one, two):
        resp = client.put(f"/api/users/{person.id}", json={"email": None}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] is None

    db.expire(one); db.refresh(one)
    db.expire(two); db.refresh(two)
    assert one.email is None and two.email is None


def test_a_missing_user_is_still_404_even_when_the_email_is_taken(client, db, auth_headers):
    """404 outranks the collision — whether a row exists elsewhere is not the
    caller's business (the by-id rule in CLAUDE.md)."""
    studio = _studio(db, "Missing")
    holder = _person(db, studio, name="Holder")

    resp = client.put(
        f"/api/users/{uuid4()}",
        json={"email": holder.email},
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text
