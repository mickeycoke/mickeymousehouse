"""/api/studio-owners must not hand one franchise's manager another
franchise's owner assignments.

THE HOLE. `get_studio_owner_or_404` was a bare primary-key
fetch with no scope check, and GET/PUT/DELETE /{assignment_id} all went through
it. The dependency is `require_franchise_management`, which admits admins AND
every franchise MANAGER (`get_managed_franchise_id` non-None). So any franchise
manager could:

  * read another franchise's studio-owner assignment (GET),
  * rewrite its notes, or set `is_active=false` — which LOCKS A LEGITIMATE
    STUDIO OWNER OUT OF THEIR OWN STUDIO (PUT),
  * deactivate it outright (DELETE).

The unfiltered list endpoint was the same hole with worse disclosure:
`_with_user_labels` attaches user_name/user_email, so it published the other
franchise's owners' PII.

WHY NO FIXTURE CAUGHT IT: the suite had no franchise-manager fixture at all —
every studio-owner test authenticated as an admin, for whom all of this is
legitimate. That fixture is built here.

Both directions are asserted: refused across franchises, and STILL WORKING
within the caller's own franchise (a fix that refuses everyone would break owner
management), plus an admin retaining full access.
"""
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User
from app.utils.password import hash_password


# ── fixtures/builders ───────────────────────────────────────────────────────

def _user(db, email, name, role="instructor"):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        db.query(StudioOwner).filter(StudioOwner.user_id == existing.id).delete()
        db.query(FranchiseOwner).filter(FranchiseOwner.user_id == existing.id).delete()
        db.delete(existing)
        db.commit()
    u = User(email=email, name=name, password_hash=hash_password("password123"),
             role=role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _studio(db, name):
    s = Studio(name=name, display_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _franchise(db, name):
    f = Franchise(name=name, is_active=True)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _link(db, franchise, studio):
    db.add(FranchiseStudio(franchise_id=franchise.id, studio_id=studio.id, is_active=True))
    db.commit()


def _assign_owner(db, user, studio, level="owner", notes="original notes"):
    row = StudioOwner(user_id=user.id, studio_id=studio.id, level=level,
                      notes=notes, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _franchise_manager(db, email, name, franchise):
    """A franchise MANAGER — the caller class `require_franchise_management`
    admits alongside admins, and the one the suite never had."""
    u = _user(db, email, name)
    db.add(FranchiseOwner(user_id=u.id, franchise_id=franchise.id,
                          level="manager", is_active=True))
    db.commit()
    return u


def _headers(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _world(db, client, tag):
    """Two franchises, one studio each, one studio-owner assignment each, and a
    manager of franchise A."""
    fa, fb = _franchise(db, f"Franchise A {tag}"), _franchise(db, f"Franchise B {tag}")
    sa, sb = _studio(db, f"Studio A {tag}"), _studio(db, f"Studio B {tag}")
    _link(db, fa, sa)
    _link(db, fb, sb)
    owner_a = _user(db, f"so-a-{tag}@test.com", "Owner A")
    owner_b = _user(db, f"so-b-{tag}@test.com", "Owner B")
    assign_a = _assign_owner(db, owner_a, sa)
    assign_b = _assign_owner(db, owner_b, sb)
    mgr_a = _franchise_manager(db, f"fmgr-a-{tag}@test.com", "Mgr A", fa)
    return {
        "mgr_a_headers": _headers(client, mgr_a.email),
        "assign_a": assign_a, "assign_b": assign_b,
        "owner_b": owner_b, "studio_b": sb, "studio_a": sa,
    }


# ── the guard is real: the fixture reaches the endpoint at all ──────────────

def test_franchise_manager_is_admitted_by_the_dependency(client, db):
    """Guards the whole file: if the manager were simply 403'd at the door, every
    "refused" assertion below would pass for the wrong reason."""
    w = _world(db, client, "adm")
    r = client.get(f"/api/studio-owners/{w['assign_a'].id}", headers=w["mgr_a_headers"])
    assert r.status_code == 200, r.text


# ── cross-franchise: refused, in all three directions ──────────────────────

def test_get_by_id_across_franchises_is_404_and_leaks_nothing(client, db):
    w = _world(db, client, "get")
    r = client.get(f"/api/studio-owners/{w['assign_b'].id}", headers=w["mgr_a_headers"])
    # 404, never 403: whether an assignment exists in another franchise is not
    # this caller's business (CLAUDE.md, "by id is not exempt").
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Studio owner assignment not found"
    body = r.text
    assert w["owner_b"].email not in body
    assert str(w["assign_b"].id) not in body
    assert str(w["studio_b"].id) not in body


def test_put_across_franchises_cannot_deactivate_another_owner(client, db):
    """The denial-of-access hole: is_active=false locks a real studio owner out."""
    w = _world(db, client, "put")
    r = client.put(f"/api/studio-owners/{w['assign_b'].id}", headers=w["mgr_a_headers"],
                   json={"is_active": False, "notes": "hijacked"})
    assert r.status_code == 404, r.text

    # Re-read the row: nothing changed.
    db.expire_all()
    row = db.query(StudioOwner).filter(StudioOwner.id == w["assign_b"].id).first()
    assert row is not None
    assert row.is_active is True
    assert row.notes == "original notes"


def test_delete_across_franchises_leaves_the_assignment_active(client, db):
    w = _world(db, client, "del")
    r = client.delete(f"/api/studio-owners/{w['assign_b'].id}", headers=w["mgr_a_headers"])
    assert r.status_code == 404, r.text

    db.expire_all()
    row = db.query(StudioOwner).filter(StudioOwner.id == w["assign_b"].id).first()
    assert row is not None
    assert row.is_active is True


def test_list_does_not_disclose_another_franchises_owner_pii(client, db):
    """`_with_user_labels` puts user_email in the list body — this is where the
    PII actually leaked."""
    w = _world(db, client, "list")
    r = client.get("/api/studio-owners", headers=w["mgr_a_headers"])
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert str(w["assign_a"].id) in ids          # own franchise still listed
    assert str(w["assign_b"].id) not in ids
    assert w["owner_b"].email not in r.text
    assert str(w["studio_b"].id) not in r.text


def test_list_filtered_by_another_franchises_studio_returns_nothing(client, db):
    """A studio_id filter must not become a way to aim the list elsewhere."""
    w = _world(db, client, "listf")
    r = client.get(f"/api/studio-owners?studio_id={w['studio_b'].id}",
                   headers=w["mgr_a_headers"])
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_post_across_franchises_is_still_refused(client, db):
    """The pre-existing escalation guard on POST stays intact after the refactor
    (403 there, because the caller named the studio itself)."""
    w = _world(db, client, "post")
    newbie = _user(db, "so-new-post@test.com", "Newbie")
    r = client.post("/api/studio-owners", headers=w["mgr_a_headers"],
                    json={"user_id": str(newbie.id), "studio_id": str(w["studio_b"].id)})
    assert r.status_code == 403, r.text
    assert db.query(StudioOwner).filter(StudioOwner.user_id == newbie.id).count() == 0


# ── own franchise: still fully working ──────────────────────────────────────

def test_manager_can_still_read_update_and_delete_own_franchise(client, db):
    w = _world(db, client, "own")
    aid = str(w["assign_a"].id)
    h = w["mgr_a_headers"]

    got = client.get(f"/api/studio-owners/{aid}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == aid

    upd = client.put(f"/api/studio-owners/{aid}", headers=h, json={"notes": "mine to edit"})
    assert upd.status_code == 200, upd.text
    db.expire_all()
    assert db.query(StudioOwner).filter(StudioOwner.id == w["assign_a"].id).first().notes \
        == "mine to edit"

    rm = client.delete(f"/api/studio-owners/{aid}", headers=h)
    assert rm.status_code == 200, rm.text
    db.expire_all()
    assert db.query(StudioOwner).filter(
        StudioOwner.id == w["assign_a"].id).first().is_active is False


def test_manager_can_still_assign_within_own_franchise(client, db):
    w = _world(db, client, "ownpost")
    newbie = _user(db, "so-new-own@test.com", "Newbie Own")
    r = client.post("/api/studio-owners", headers=w["mgr_a_headers"],
                    json={"user_id": str(newbie.id), "studio_id": str(w["studio_a"].id)})
    assert r.status_code == 201, r.text


# ── admin keeps full access ─────────────────────────────────────────────────

def test_admin_retains_access_to_every_franchise(client, auth_headers, db):
    w = _world(db, client, "admin")
    for key in ("assign_a", "assign_b"):
        aid = str(w[key].id)
        assert client.get(f"/api/studio-owners/{aid}", headers=auth_headers).status_code == 200
        upd = client.put(f"/api/studio-owners/{aid}", headers=auth_headers,
                         json={"notes": "admin edit"})
        assert upd.status_code == 200, upd.text
    listing = client.get("/api/studio-owners", headers=auth_headers)
    assert listing.status_code == 200
    ids = {row["id"] for row in listing.json()}
    assert {str(w["assign_a"].id), str(w["assign_b"].id)} <= ids


def test_admin_scoped_by_x_studio_id_is_bound_to_that_studio(client, auth_headers, db):
    """X-Studio-Id binds admins too (CLAUDE.md). An admin operating inside
    studio A may not reach studio B's assignment by id."""
    w = _world(db, client, "xsid")
    h = {**auth_headers, "X-Studio-Id": str(w["studio_a"].id)}
    assert client.get(f"/api/studio-owners/{w['assign_a'].id}", headers=h).status_code == 200
    r = client.get(f"/api/studio-owners/{w['assign_b'].id}", headers=h)
    assert r.status_code == 404, r.text
    assert w["owner_b"].email not in r.text
