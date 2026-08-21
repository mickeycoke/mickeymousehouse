"""Studio (and franchise) isolation, asserted over HTTP — the CI gate.

`test_studio_scoping.py` proves the repo layer is correct by constructing an
`AccessScope` by hand and calling repo methods. That is necessary but not
sufficient: it never issues a request, so it cannot see an endpoint that
skips the repo entirely, or a permission check that forgets to thread the
operating studio through. This file goes through the API the way a browser
does.

RULE BEING ENFORCED:
  * a caller operating in studio A never sees studio B's rows — in a list OR
    by primary key
  * a by-id fetch of another studio's (or franchise's) row returns 404, never 200
  * a write to another studio's row is refused
  * a row with NULL studio_id is invisible to everyone
  * `X-Studio-Id` binds admins too — an admin who has narrowed to one studio
    is scoped exactly like that studio's own staff, never wider

A FAILURE HERE IS A SECURITY BUG, NOT A FLAKY TEST. Do not skip, xfail, or
delete a case to make the build green — fix the endpoint.
"""
from uuid import uuid4

import pytest

from app.models.studio import Studio
from app.models.user import User
from app.utils.password import hash_password


# ─── world builder ───────────────────────────────────────────────────────────

def _studio(db, label):
    s = Studio(name=f"{label}-{uuid4().hex[:6]}", display_name=label, is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    return s


@pytest.fixture
def world(db):
    """Two studios, A and B."""
    return {"a": _studio(db, "IsolationA"), "b": _studio(db, "IsolationB")}


def as_studio(headers, studio):
    """Operate as a specific studio. X-Studio-Id is admin-only and is exactly
    how an admin (and an impersonation token) narrows to one studio."""
    return {**headers, "X-Studio-Id": str(studio.id)}


# ─── privilege escalation ────────────────────────────────────────────────────

def test_studio_owner_assignment_cannot_target_a_foreign_studio(client, auth_headers, db, world):
    """The highest-severity finding class: a franchise manager could post an
    assignment for ANY studio, making themselves its owner; every downstream
    guard then passes legitimately. The endpoint must at minimum validate
    that the target studio is one the caller may manage, so a
    non-manageable studio is never silently accepted.
    """
    victim = _studio(db, "VictimStudio")
    u = User(email=f"esc-{uuid4().hex[:8]}@permtests.com", name="Escalator",
             password_hash=hash_password("password123"), role="instructor", is_active=True)
    db.add(u); db.commit(); db.refresh(u)

    r = client.post("/api/studio-owners",
                    headers=as_studio(auth_headers, world["a"]),
                    json={"user_id": str(u.id), "studio_id": str(victim.id), "level": "owner"})
    assert r.status_code in (400, 403, 404), (
        "an owner assignment was accepted for a studio outside the caller's scope "
        f"(got {r.status_code}) — this is privilege escalation"
    )


# ─── studio-owner assignments by id ──────────────────────────────────────────
# `get_studio_owner_or_404` used to be a bare primary-key fetch, and
# `require_franchise_management` admits every franchise MANAGER — so any
# manager holding an id could GET another franchise's owner assignment, PUT
# `is_active=false` to lock that owner out of their own studio, or DELETE it.
# The rule: the by-id paths apply the SAME scope the list applies — a row you
# cannot see in the list is a row you cannot fetch or modify by id, and the
# refusal is a 404 indistinguishable from a genuinely missing row.

def _franchise_manager(db, franchise, label):
    """A login-capable user who MANAGES the franchise (level='manager')."""
    from app.models.franchise_owner import FranchiseOwner
    u = User(email=f"{label}-{uuid4().hex[:8]}@permtests.com", name=label,
             password_hash=hash_password("password123"), role="instructor", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    db.add(FranchiseOwner(user_id=u.id, franchise_id=franchise.id,
                          level="manager", is_active=True))
    db.commit()
    return u


def _owner_assignment(db, studio, label):
    """A StudioOwner row at the studio, pointing at a real user."""
    from app.models.studio_owner import StudioOwner
    u = User(email=f"{label}-{uuid4().hex[:8]}@permtests.com", name=label,
             password_hash=hash_password("password123"), role="instructor", is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    row = StudioOwner(user_id=u.id, studio_id=studio.id, level="owner", is_active=True)
    db.add(row); db.commit(); db.refresh(row)
    return row


def _login(client, user):
    r = client.post("/api/auth/login",
                    json={"email": user.email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def franchise_world(db, world):
    """Two franchises, one studio each (reusing `world`'s studios), an owner
    assignment in each, and a manager who runs franchise A only."""
    from app.models.franchise import Franchise
    from app.models.franchise_studio import FranchiseStudio
    fa = Franchise(name=f"FranA-{uuid4().hex[:6]}", is_active=True)
    fb = Franchise(name=f"FranB-{uuid4().hex[:6]}", is_active=True)
    db.add_all([fa, fb]); db.commit()
    db.add_all([
        FranchiseStudio(franchise_id=fa.id, studio_id=world["a"].id, is_active=True),
        FranchiseStudio(franchise_id=fb.id, studio_id=world["b"].id, is_active=True),
    ])
    db.commit()
    return {
        **world,
        "mgr_a": _franchise_manager(db, fa, "fran-mgr-a"),
        "row_a": _owner_assignment(db, world["a"], "owner-a"),
        "row_b": _owner_assignment(db, world["b"], "owner-b"),
        "fran_a": fa,
        "fran_b": fb,
    }


def test_studio_owner_get_across_franchises_is_404_and_indistinguishable(
    client, db, franchise_world
):
    """Franchise A's manager fetches franchise B's assignment by id: 404, with
    the exact body a nonexistent id produces — existence is not disclosed."""
    hdrs = _login(client, franchise_world["mgr_a"])
    foreign = client.get(f"/api/studio-owners/{franchise_world['row_b'].id}", headers=hdrs)
    missing = client.get(f"/api/studio-owners/{uuid4()}", headers=hdrs)
    assert foreign.status_code == 404, (
        f"cross-franchise by-id GET returned {foreign.status_code}, expected 404"
    )
    assert missing.status_code == 404
    assert foreign.json() == missing.json(), (
        "a foreign row's 404 body differs from a missing row's — existence leaks"
    )


def test_studio_owner_update_across_franchises_is_404(client, db, franchise_world):
    hdrs = _login(client, franchise_world["mgr_a"])
    r = client.put(f"/api/studio-owners/{franchise_world['row_b'].id}",
                   headers=hdrs, json={"is_active": False, "notes": "locked out"})
    assert r.status_code == 404, (
        f"cross-franchise PUT returned {r.status_code} — a manager can lock "
        "another franchise's owner out of their own studio"
    )
    db.refresh(franchise_world["row_b"])
    assert franchise_world["row_b"].is_active is True, "the foreign row was modified"


def test_studio_owner_delete_across_franchises_is_404(client, db, franchise_world):
    hdrs = _login(client, franchise_world["mgr_a"])
    r = client.delete(f"/api/studio-owners/{franchise_world['row_b'].id}", headers=hdrs)
    assert r.status_code == 404, f"cross-franchise DELETE returned {r.status_code}"
    db.refresh(franchise_world["row_b"])
    assert franchise_world["row_b"].is_active is True, "the foreign row was deactivated"


def test_studio_owner_manager_still_operates_on_own_franchise(client, db, franchise_world):
    """The legitimate path must not break: same scope as the list, so a
    manager's own franchise's rows remain fully reachable by id."""
    hdrs = _login(client, franchise_world["mgr_a"])
    own_id = franchise_world["row_a"].id
    assert client.get(f"/api/studio-owners/{own_id}", headers=hdrs).status_code == 200
    r = client.put(f"/api/studio-owners/{own_id}", headers=hdrs, json={"notes": "ok"})
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == "ok"
    r = client.delete(f"/api/studio-owners/{own_id}", headers=hdrs)
    assert r.status_code == 200, r.text
    db.refresh(franchise_world["row_a"])
    assert franchise_world["row_a"].is_active is False


def test_studio_owner_admin_still_reaches_any_franchise_by_id(
    client, auth_headers, db, franchise_world
):
    """An unrestricted admin (no X-Studio-Id) keeps full reach."""
    for row in (franchise_world["row_a"], franchise_world["row_b"]):
        r = client.get(f"/api/studio-owners/{row.id}", headers=auth_headers)
        assert r.status_code == 200, r.text
    r = client.put(f"/api/studio-owners/{franchise_world['row_b'].id}",
                   headers=auth_headers, json={"notes": "admin touch"})
    assert r.status_code == 200, r.text


def test_studio_owner_list_is_franchise_scoped(client, db, franchise_world):
    """The scope the by-id paths mirror: franchise B's rows (and their owner
    emails) never appear in franchise A's manager's list."""
    hdrs = _login(client, franchise_world["mgr_a"])
    r = client.get("/api/studio-owners", headers=hdrs)
    assert r.status_code == 200, r.text
    row_ids = {row["id"] for row in r.json()}
    assert str(franchise_world["row_a"].id) in row_ids, "own franchise's row missing"
    assert str(franchise_world["row_b"].id) not in row_ids, (
        "another franchise's owner assignment leaked into the list"
    )


# ─── users by id (admin operating-studio scoping) ────────────────────────────
# `get_user` (no dependency at all), `update_user`, and `delete_user` (both
# calling `_require_user_admin` with NO `operating_studio_id` arg) never
# threaded the X-Studio-Id-derived operating studio into their scope checks —
# even though `_require_user_admin` already accepts that parameter and
# `list_users`/`create_user`/`get_user_pin`/`set_user_pin` in the same file
# already thread it correctly. Result: an admin narrowed to studio A via
# X-Studio-Id could still GET/PUT/DELETE a studio B user by id, even though
# that same user is correctly hidden from `GET /api/users`'s list.

def _staff_user(db, studio_id, label, role="instructor"):
    u = User(email=f"{label}-{uuid4().hex[:8]}@permtests.com", name=label,
             password_hash=hash_password("password123"), role=role,
             studio_id=studio_id, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_user_get_across_operating_studio_is_404(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "cross-get")
    r = client.get(f"/api/users/{target.id}", headers=as_studio(auth_headers, world["a"]))
    assert r.status_code == 404, \
        f"admin scoped to studio A read studio B's user by id (got {r.status_code})"


def test_user_update_across_operating_studio_is_refused(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "cross-put")
    r = client.put(f"/api/users/{target.id}", headers=as_studio(auth_headers, world["a"]),
                   json={"name": "OVERWRITTEN BY STUDIO A"})
    assert r.status_code in (403, 404), \
        f"admin scoped to studio A updated studio B's user (got {r.status_code})"
    db.refresh(target)
    assert target.name != "OVERWRITTEN BY STUDIO A", "studio B's user was rewritten"


def test_user_delete_across_operating_studio_is_refused(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "cross-delete")
    r = client.delete(f"/api/users/{target.id}", headers=as_studio(auth_headers, world["a"]))
    assert r.status_code in (403, 404), \
        f"admin scoped to studio A deleted studio B's user (got {r.status_code})"
    db.refresh(target)
    assert target.is_active is True, "studio B's user was deactivated"


def test_user_get_update_delete_within_operating_studio_still_works(client, auth_headers, db, world):
    """False-positive-proof pair for the three cases above: the SAME admin,
    scoped to the target user's OWN studio (X-Studio-Id=B), must still
    succeed — otherwise the 404/403s above would prove nothing."""
    target = _staff_user(db, world["b"].id, "same-studio")
    hdr = as_studio(auth_headers, world["b"])
    assert client.get(f"/api/users/{target.id}", headers=hdr).status_code == 200
    r = client.put(f"/api/users/{target.id}", headers=hdr, json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert client.delete(f"/api/users/{target.id}", headers=hdr).status_code == 200


def test_user_get_update_delete_unrestricted_admin_still_works(client, auth_headers, db, world):
    """Same admin, no X-Studio-Id at all: unrestricted, exactly as before this
    fix — the fix must only narrow a SCOPED admin, never an unscoped one."""
    target = _staff_user(db, world["b"].id, "unrestricted")
    assert client.get(f"/api/users/{target.id}", headers=auth_headers).status_code == 200
    r = client.put(f"/api/users/{target.id}", headers=auth_headers, json={"name": "Renamed Too"})
    assert r.status_code == 200, r.text
    assert client.delete(f"/api/users/{target.id}", headers=auth_headers).status_code == 200


# ─── users by id: admin role-gate exemption is a STUDIO boundary, not a ROLE
# boundary ─────────────────────────────────────────────────────────────────
# Threading `operating_studio_id` into `_require_user_admin` for
# `update_user`/`delete_user` correctly turns `managed` into a real
# `{studio}` set for a scoped admin instead of always `None`. But
# `_require_target_in_scope` used that same non-`None` `managed` to ALSO
# apply `SCOPED_ASSIGNABLE_ROLES` — a rule written for non-admin studio
# owners/managers ("they can never touch admins, managers, or fellow
# owners", `SCOPED_ASSIGNABLE_ROLES`'s own comment) — to the admin caller
# too. A scoped admin acting on a manager/admin colleague, or on their OWN
# account, WITHIN their own operating studio then hit that gate and got a
# spurious 403 — a capability that worked unconditionally for any admin
# otherwise.
#
# The fix: `_require_target_in_scope` takes an explicit `is_admin` flag and
# only applies the ROLE gate when the caller is NOT an admin. The STUDIO gate
# (`target.studio_id not in managed`) still applies to everyone, admin or not.

def _scoped_admin(db, studio_id, label):
    """A second, login-capable admin — NOT the shared `admin_user` fixture —
    homed at `studio_id`, so self-edit can be exercised with a real token
    without mutating the shared admin row other test files also depend on."""
    u = User(email=f"{label}-{uuid4().hex[:8]}@permtests.com", name=label,
             password_hash=hash_password("password123"), role="admin",
             studio_id=studio_id, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_user_update_delete_scoped_admin_on_instructor_still_works(client, auth_headers, db, world):
    """Case (a) — unchanged baseline: a scoped admin acting on a Studio-A
    instructor (a SCOPED_ASSIGNABLE_ROLES role) keeps working exactly as
    before this fix."""
    hdr = as_studio(auth_headers, world["a"])
    target = _staff_user(db, world["a"].id, "role-gate-instructor", role="instructor")
    r = client.put(f"/api/users/{target.id}", headers=hdr, json={"name": "Renamed Instructor"})
    assert r.status_code == 200, r.text

    target2 = _staff_user(db, world["a"].id, "role-gate-instructor-del", role="instructor")
    assert client.delete(f"/api/users/{target2.id}", headers=hdr).status_code == 200


def test_user_update_delete_scoped_admin_on_manager_colleague_now_works(client, auth_headers, db, world):
    """Case (b) — the actual regression fix: a scoped admin must be able to
    manage a 'manager'-role colleague sitting in THEIR OWN operating studio.
    Only the studio boundary is new; there is no new role boundary for an
    admin. This is the case that was completely untested before and is the
    proof of the regression."""
    hdr = as_studio(auth_headers, world["a"])
    target = _staff_user(db, world["a"].id, "role-gate-manager", role="manager")
    r = client.put(f"/api/users/{target.id}", headers=hdr, json={"name": "Renamed Manager"})
    assert r.status_code == 200, (
        "scoped admin could not edit a manager-role colleague in their own "
        f"operating studio (got {r.status_code}: {r.text})"
    )
    assert r.json()["name"] == "Renamed Manager"

    target2 = _staff_user(db, world["a"].id, "role-gate-manager-del", role="manager")
    r2 = client.delete(f"/api/users/{target2.id}", headers=hdr)
    assert r2.status_code == 200, (
        "scoped admin could not deactivate a manager-role colleague in their "
        f"own operating studio (got {r2.status_code}: {r2.text})"
    )


def test_user_update_delete_scoped_admin_on_admin_colleague_now_works(client, auth_headers, db, world):
    """Case (b) continued: same for a fellow admin sitting in the operating
    studio — 'admin' is also outside SCOPED_ASSIGNABLE_ROLES, and this is
    exactly the shape of "a scoped admin managing a fellow admin"."""
    hdr = as_studio(auth_headers, world["a"])
    target = _staff_user(db, world["a"].id, "role-gate-admin-colleague", role="admin")
    r = client.put(f"/api/users/{target.id}", headers=hdr, json={"name": "Renamed Admin"})
    assert r.status_code == 200, (
        "scoped admin could not edit a fellow admin in their own operating "
        f"studio (got {r.status_code}: {r.text})"
    )


def test_user_update_delete_scoped_admin_on_self_now_works(client, db, world):
    """Case (b) continued: the caller's OWN account, when it sits in the
    operating studio, must be editable/deactivatable exactly like any
    unrestricted admin could before this fix. Uses a dedicated second admin
    (not the shared `admin_user` fixture) so this test does not mutate state
    other test files rely on."""
    actor = _scoped_admin(db, world["a"].id, "role-gate-self-admin")
    hdr = as_studio(_login(client, actor), world["a"])

    r = client.put(f"/api/users/{actor.id}", headers=hdr, json={"name": "Renamed Self"})
    assert r.status_code == 200, (
        "scoped admin could not edit their OWN account in their own "
        f"operating studio (got {r.status_code}: {r.text})"
    )
    assert r.json()["name"] == "Renamed Self"

    r2 = client.delete(f"/api/users/{actor.id}", headers=hdr)
    assert r2.status_code == 200, (
        "scoped admin could not deactivate their OWN account in their own "
        f"operating studio (got {r2.status_code}: {r2.text})"
    )


def test_global_admin_self_edit_while_operating_a_studio_still_works(client, db, world):
    """The REAL, common shape of an admin account is global: studio_id=NULL
    (the seeded admin@example.com account is exactly this shape). A NULL
    studio_id can never be `in` a `managed` set containing one concrete
    operating-studio UUID, so a global admin editing/deactivating THEMSELVES
    while operating any studio at all would 403 unconditionally without the
    is_admin self-bypass in `_require_target_in_scope`. This test uses a
    NULL-studio_id admin specifically so a regression of the self-bypass
    can't hide behind a fixture that happens to satisfy the studio gate on
    its own."""
    global_admin = User(email=f"global-admin-{uuid4().hex[:8]}@permtests.com", name="Global Admin",
                        password_hash=hash_password("password123"), role="admin",
                        studio_id=None, is_active=True)
    db.add(global_admin); db.commit(); db.refresh(global_admin)
    assert global_admin.studio_id is None

    hdr = as_studio(_login(client, global_admin), world["a"])

    r = client.put(f"/api/users/{global_admin.id}", headers=hdr, json={"name": "Renamed Global Self"})
    assert r.status_code == 200, (
        "a global (studio_id=NULL) admin could not edit their OWN account "
        f"while operating a studio (got {r.status_code}: {r.text})"
    )
    assert r.json()["name"] == "Renamed Global Self"

    r2 = client.delete(f"/api/users/{global_admin.id}", headers=hdr)
    assert r2.status_code == 200, (
        "a global (studio_id=NULL) admin could not deactivate their OWN "
        f"account while operating a studio (got {r2.status_code}: {r2.text})"
    )


def test_user_update_delete_scoped_admin_on_manager_other_studio_still_refused(client, auth_headers, db, world):
    """Case (c) — must NOT regress: the STUDIO boundary is still enforced for
    every role, including manager/admin. Only the ROLE gate was removed for
    admins; the studio gate was never touched."""
    hdr = as_studio(auth_headers, world["a"])
    target = _staff_user(db, world["b"].id, "role-gate-manager-cross", role="manager")

    r = client.put(f"/api/users/{target.id}", headers=hdr, json={"name": "SHOULD NOT SAVE"})
    assert r.status_code in (403, 404), (
        "scoped admin reached across studios to edit a manager-role user in a "
        f"DIFFERENT studio (got {r.status_code})"
    )
    db.refresh(target)
    assert target.name != "SHOULD NOT SAVE", "cross-studio manager was rewritten"

    r2 = client.delete(f"/api/users/{target.id}", headers=hdr)
    assert r2.status_code in (403, 404), (
        "scoped admin reached across studios to deactivate a manager-role "
        f"user in a DIFFERENT studio (got {r2.status_code})"
    )
    db.refresh(target)
    assert target.is_active is True, "cross-studio manager was deactivated"


def test_user_update_delete_nonadmin_owner_on_manager_colleague_still_refused(client, db, franchise_world):
    """Case (d) — must NOT loosen: a NON-ADMIN studio owner/manager acting on
    a fellow manager (or admin, or owner) in THEIR OWN studio must still be
    refused. Only admins get the role-gate exemption; SCOPED_ASSIGNABLE_ROLES
    still fully applies to studio owners/managers. `row_a` is
    `franchise_world`'s active StudioOwner(level='owner') at studio A."""
    owner_row = franchise_world["row_a"]
    owner_user = db.query(User).filter(User.id == owner_row.user_id).first()
    hdr = _login(client, owner_user)

    colleague = _staff_user(db, franchise_world["a"].id, "role-gate-nonadmin-mgr", role="manager")
    r = client.put(f"/api/users/{colleague.id}", headers=hdr, json={"name": "SHOULD NOT SAVE"})
    assert r.status_code == 403, (
        "a non-admin studio owner edited a manager-role colleague in their "
        f"OWN studio — SCOPED_ASSIGNABLE_ROLES must still refuse this (got {r.status_code})"
    )
    db.refresh(colleague)
    assert colleague.name != "SHOULD NOT SAVE", "colleague was rewritten by a non-admin owner"

    r2 = client.delete(f"/api/users/{colleague.id}", headers=hdr)
    assert r2.status_code == 403, (
        "a non-admin studio owner deactivated a manager-role colleague in "
        f"their OWN studio (got {r2.status_code})"
    )
    db.refresh(colleague)
    assert colleague.is_active is True, "colleague was deactivated by a non-admin owner"


# ─── invite / setup-link (admin operating-studio scoping) ────────────────────
# `auth._may_manage_user` (used by `POST /api/auth/invite`) unconditionally
# returned True for ANY admin, ignoring `operating_studio_id` entirely — an
# admin narrowed to studio A via X-Studio-Id could still mint an invite email
# for a studio B user. `POST /api/auth/setup-link` reuses
# `users._require_user_admin` + `_require_target_in_scope` directly (see that
# route's docstring) and was ALREADY correctly scoped before this fix — its
# cases below just prove the invariant, matching this file's rule that a
# guard is only trustworthy once it's asserted over HTTP.

def test_invite_across_operating_studio_is_refused(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "invite-cross")
    r = client.post("/api/auth/invite", headers=as_studio(auth_headers, world["a"]),
                    json={"user_id": str(target.id)})
    assert r.status_code == 403, \
        f"admin scoped to studio A invited studio B's user (got {r.status_code})"


def test_invite_within_operating_studio_still_works(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "invite-same")
    r = client.post("/api/auth/invite", headers=as_studio(auth_headers, world["b"]),
                    json={"user_id": str(target.id)})
    assert r.status_code == 200, r.text


def test_setup_link_across_operating_studio_is_refused(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "setup-link-cross")
    r = client.post("/api/auth/setup-link", headers=as_studio(auth_headers, world["a"]),
                    json={"user_id": str(target.id)})
    assert r.status_code == 403, \
        f"admin scoped to studio A issued a setup link for studio B's user (got {r.status_code})"


def test_setup_link_within_operating_studio_still_works(client, auth_headers, db, world):
    target = _staff_user(db, world["b"].id, "setup-link-same")
    r = client.post("/api/auth/setup-link", headers=as_studio(auth_headers, world["b"]),
                    json={"user_id": str(target.id)})
    assert r.status_code == 200, r.text
