"""Studio (and franchise) isolation proof, at the data layer.

One shared implementation (`app/data/base.py`'s `StudioScopedRepo` /
`FranchiseScopedRepo` / `DerivedScopeRepo`) backs every scoped repo — that is
the whole point of `app/data/`. This file pins its policy directly, using the
production `FranchiseStudioRepo` where a real repo exists, and small
test-local repo subclasses (identical in shape to a real one — same base
class, same `model =` attribute) over other real, already-scoped models
where no production repo has been written yet. Either way this is the SAME
`app/data/base.py` code under test, never a reimplementation.

Owner policy being asserted:
  * a scoped user sees ONLY rows belonging to their own studio
  * a row with NO studio_id is invisible — no fallback, no shared bucket
  * an admin with no operating studio selected sees everything
  * an admin who selects a studio is scoped exactly like that studio
  * a "derived" model (no scope column of its own) inherits its parent's
    studio scope, never trusts a caller-supplied id directly
  * on the franchise axis, NULL franchise_id means "shared standard,
    visible to everyone" — deliberately the OPPOSITE of the studio axis
"""
from uuid import uuid4

import pytest

from app.data.base import DerivedScopeRepo, StudioScopedRepo, FranchiseScopedRepo
from app.data.franchise_studio_repo import FranchiseStudioRepo
from app.data.scope import AccessScope
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio import Studio
from app.models.user import User
from app.models.user_question import UserQuestion, UserQuestionMessage
from app.utils.password import hash_password


# ─── test-local repos ─────────────────────────────────────────────────────
# Same shape as a production repo (see app/data/franchise_studio_repo.py /
# studio_subscriptions.py) — just bound to a model that has no dedicated repo
# file yet, so the shared base-class behavior can be pinned against it too.

class _UserScopeRepo(StudioScopedRepo):
    model = User


class _UserQuestionScopeRepo(StudioScopedRepo):
    model = UserQuestion


class _UserQuestionMessageRepo(DerivedScopeRepo):
    model = UserQuestionMessage
    parent_repo_cls = _UserQuestionScopeRepo
    parent_fk = "question_id"


class _FranchiseOwnerScopeRepo(FranchiseScopedRepo):
    model = FranchiseOwner


# ─── fixtures ────────────────────────────────────────────────────────────────

def make_studio(db, label):
    s = Studio(name=f"{label} {uuid4().hex[:6]}", display_name=label, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def make_franchise(db, label):
    f = Franchise(name=f"{label} {uuid4().hex[:6]}", is_active=True)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def make_staff(db, studio_id):
    u = User(
        email=f"scope-{uuid4().hex[:8]}@permtests.com",
        name="Scope Staff",
        password_hash=hash_password("password123"),
        role="instructor",
        studio_id=studio_id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def scope_for(db, user, operating_studio_id=None):
    """Build an AccessScope the same way the FastAPI dependency does."""
    from app.utils.ownership import get_client_visibility_studio_ids

    visible = get_client_visibility_studio_ids(
        db, user, operating_studio_id=operating_studio_id
    )
    return AccessScope(
        user=user,
        operating_studio_id=operating_studio_id,
        visible_studio_ids=None if visible is None else frozenset(visible),
        visible_franchise_id=None,
    )


@pytest.fixture
def two_studios(db):
    """Studio A, studio B, and an orphan (studio-less) row on the `User`
    studio axis, plus a franchise<->studio link per studio for the
    FranchiseStudioRepo tests."""
    a, b = make_studio(db, "ScopeA"), make_studio(db, "ScopeB")
    fa, fb = make_franchise(db, "FranA"), make_franchise(db, "FranB")

    link_a = FranchiseStudio(franchise_id=fa.id, studio_id=a.id, is_active=True)
    link_b = FranchiseStudio(franchise_id=fb.id, studio_id=b.id, is_active=True)
    db.add_all([link_a, link_b])
    db.commit()
    db.refresh(link_a)
    db.refresh(link_b)

    staff_a = make_staff(db, a.id)
    staff_b = make_staff(db, b.id)
    orphan_staff = User(
        email=f"orphan-{uuid4().hex[:8]}@permtests.com", name="Orphan Staff",
        password_hash=hash_password("password123"), role="instructor",
        studio_id=None, is_active=True,
    )
    db.add(orphan_staff)
    db.commit()
    db.refresh(orphan_staff)

    return {
        "a": a, "b": b, "fa": fa, "fb": fb,
        "link_a": link_a, "link_b": link_b,
        "staff_a": staff_a, "staff_b": staff_b, "orphan_staff": orphan_staff,
    }


# ─── studio axis (StudioScopedRepo), via the real production repo ────────────

def test_franchise_studio_scoped_to_own_studio(db, two_studios):
    t = two_studios
    repo = FranchiseStudioRepo(db, scope_for(db, t["staff_a"]))
    ids = {row.id for row in repo.all()}

    assert t["link_a"].id in ids
    assert t["link_b"].id not in ids, "another studio's franchise link leaked"


def test_franchise_studio_get_or_404_hides_other_studios(db, two_studios):
    from fastapi import HTTPException

    t = two_studios
    repo = FranchiseStudioRepo(db, scope_for(db, t["staff_a"]))
    assert repo.get_or_404(t["link_a"].id).id == t["link_a"].id
    with pytest.raises(HTTPException) as exc:
        repo.get_or_404(t["link_b"].id)
    assert exc.value.status_code == 404, "must 404, not 403 — existence is itself private"


def test_admin_without_operating_studio_sees_everything(db, two_studios, admin_user):
    t = two_studios
    repo = FranchiseStudioRepo(db, scope_for(db, admin_user))
    ids = {row.id for row in repo.all()}
    assert {t["link_a"].id, t["link_b"].id} <= ids


def test_admin_operating_in_studio_is_scoped_like_that_studio(db, two_studios, admin_user):
    """Impersonation / studio-selection must scope an admin exactly like the
    studio's own staff."""
    t = two_studios
    repo = FranchiseStudioRepo(db, scope_for(db, admin_user, operating_studio_id=t["a"].id))
    ids = {row.id for row in repo.all()}

    assert t["link_a"].id in ids
    assert t["link_b"].id not in ids


# ─── studio axis: NULL studio_id is invisible, no fallback ───────────────────
# `User.studio_id` is nullable in production and there is no dedicated
# UserRepo yet, so this uses a repo bound to the real `User` model — same
# base class, same policy, just not yet wired into a route.

def test_orphan_studio_id_is_invisible(db, two_studios):
    t = two_studios
    repo = _UserScopeRepo(db, scope_for(db, t["staff_a"]))
    ids = {u.id for u in repo.all()}

    assert t["staff_a"].id in ids
    assert t["staff_b"].id not in ids, "another studio's user leaked"
    assert t["orphan_staff"].id not in ids, "studio-less user leaked — no fallback bucket"


def test_admin_operating_studio_scopes_the_orphan_check_too(db, two_studios, admin_user):
    t = two_studios
    repo = _UserScopeRepo(db, scope_for(db, admin_user, operating_studio_id=t["a"].id))
    ids = {u.id for u in repo.all()}
    assert t["staff_b"].id not in ids
    assert t["orphan_staff"].id not in ids


# ─── create-path stamping ────────────────────────────────────────────────────

def test_stamp_new_uses_operating_studio(db, two_studios, admin_user):
    t = two_studios
    repo = _UserScopeRepo(db, scope_for(db, admin_user, operating_studio_id=t["a"].id))
    stamped = repo.stamp_new(email=f"stamped-{uuid4().hex[:8]}@permtests.com", name="Stamped",
                             password_hash=hash_password("x"), role="instructor")
    assert stamped.studio_id == t["a"].id


def test_stamp_new_uses_own_studio_for_scoped_staff(db, two_studios):
    t = two_studios
    repo = _UserScopeRepo(db, scope_for(db, t["staff_a"]))
    stamped = repo.stamp_new(email=f"stamped2-{uuid4().hex[:8]}@permtests.com", name="Stamped",
                             password_hash=hash_password("x"), role="instructor")
    assert stamped.studio_id == t["a"].id


def test_stamp_new_never_creates_an_invisible_row(db, two_studios):
    """Regression guard: a multi-studio caller with no operating studio
    selected must never get studio_id=None — that would be silent data loss
    (a 201 followed by a row invisible to its own creator). Refuse instead
    and make the caller pick."""
    from fastapi import HTTPException

    t = two_studios
    multi = AccessScope(
        user=t["staff_a"],
        operating_studio_id=None,
        visible_studio_ids=frozenset({t["a"].id, t["b"].id}),
        visible_franchise_id=None,
    )
    with pytest.raises(HTTPException) as exc:
        _UserScopeRepo(db, multi).stamp_new(
            email=f"ambiguous-{uuid4().hex[:8]}@permtests.com", name="Ambiguous",
            password_hash=hash_password("x"), role="instructor",
        )
    assert exc.value.status_code == 422


def test_stamp_new_rejects_another_studio(db, two_studios):
    """A scoped user may not plant a record in someone else's studio."""
    from fastapi import HTTPException

    t = two_studios
    repo = _UserScopeRepo(db, scope_for(db, t["staff_a"]))
    with pytest.raises(HTTPException) as exc:
        repo.stamp_new(
            email=f"sneaky-{uuid4().hex[:8]}@permtests.com", name="Sneaky",
            password_hash=hash_password("x"), role="instructor", studio_id=t["b"].id,
        )
    assert exc.value.status_code == 403


# ─── derived: no scope column of its own, inherits the parent's ──────────────

def test_derived_model_inherits_its_parents_studio_scope(db, two_studios):
    """A UserQuestionMessage has no studio_id — its visibility must come from
    its parent UserQuestion's studio (via user_id), never a caller-trusted id."""
    t = two_studios
    q_mine = UserQuestion(user_id=t["staff_a"].id, studio_id=t["a"].id, status="new")
    q_theirs = UserQuestion(user_id=t["staff_b"].id, studio_id=t["b"].id, status="new")
    db.add_all([q_mine, q_theirs])
    db.commit()
    db.refresh(q_mine)
    db.refresh(q_theirs)

    msg_mine = UserQuestionMessage(question_id=q_mine.id, author_user_id=t["staff_a"].id,
                                   is_admin_reply=False, body="mine")
    msg_theirs = UserQuestionMessage(question_id=q_theirs.id, author_user_id=t["staff_b"].id,
                                     is_admin_reply=False, body="theirs")
    db.add_all([msg_mine, msg_theirs])
    db.commit()
    db.refresh(msg_mine)
    db.refresh(msg_theirs)

    repo = _UserQuestionMessageRepo(db, scope_for(db, t["staff_a"]))
    ids = {m.id for m in repo.all()}
    assert msg_mine.id in ids
    assert msg_theirs.id not in ids, "another studio's thread message leaked via its parent"


# ─── franchise axis: NULL means shared, the OPPOSITE of the studio axis ──────

def test_franchise_owner_scoped_to_own_franchise(db, two_studios):
    t = two_studios
    owner_a = FranchiseOwner(user_id=t["staff_a"].id, franchise_id=t["fa"].id, level="owner")
    owner_b = FranchiseOwner(user_id=t["staff_b"].id, franchise_id=t["fb"].id, level="owner")
    db.add_all([owner_a, owner_b])
    db.commit()
    db.refresh(owner_a)
    db.refresh(owner_b)

    scope = AccessScope(
        user=t["staff_a"], operating_studio_id=None,
        visible_studio_ids=frozenset({t["a"].id}), visible_franchise_id=t["fa"].id,
    )
    ids = {row.id for row in _FranchiseOwnerScopeRepo(db, scope).all()}
    assert owner_a.id in ids
    assert owner_b.id not in ids, "another franchise's owner row leaked"


def test_franchise_axis_admin_unrestricted_without_operating_studio(db, two_studios, admin_user):
    """Mirrors the studio axis: `FranchiseScopedRepo` is unrestricted only for
    an admin with no operating studio selected — see its `_apply_scope`."""
    t = two_studios
    owner_a = FranchiseOwner(user_id=t["staff_a"].id, franchise_id=t["fa"].id, level="owner")
    db.add(owner_a)
    db.commit()
    db.refresh(owner_a)

    scope = AccessScope(
        user=admin_user, operating_studio_id=None,
        visible_studio_ids=None, visible_franchise_id=None,
    )
    ids = {row.id for row in _FranchiseOwnerScopeRepo(db, scope).all()}
    assert owner_a.id in ids


# `FranchiseOwner.franchise_id` is NOT NULL in production (an assignment
# always names its franchise), so no shipped table exercises the "NULL
# franchise_id = shared standard" branch end-to-end. The branch itself is
# still real, load-bearing code in `FranchiseScopedRepo._apply_scope`
# (app/data/base.py) — `col == scope.visible_franchise_id OR col IS NULL` —
# ready for the next franchise-scoped model with an optional franchise_id
# (the same shape CustomMetricDefinition had in the app this kit was cut
# from). This file documents that contract rather than faking a nullable
# column onto a model that does not have one.


# ─── "see nothing" is a real state, not "see everything" ─────────────────────

def test_portal_login_never_gets_unrestricted_scope(db, two_studios):
    """`get_client_visibility_studio_ids` returns None ("unrestricted") for
    admins AND for staff with no studio attachment (head-office users). A
    portal login has no attachment either, so it must not land in the same
    branch — clamped in `get_scope`, not in each route."""
    from app.data.scope import get_scope

    portal = User(
        email=f"portal-{uuid4().hex[:8]}@permtests.com",
        name="Portal Login",
        password_hash=hash_password("password123"),
        role="client",
        studio_id=None,
        is_active=True,
    )
    db.add(portal)
    db.commit()
    db.refresh(portal)

    scope = get_scope(db=db, current_user=portal, operating_studio_id=None)
    assert scope.visible_studio_ids == frozenset(), "portal login must see nothing"
    assert not scope.is_unrestricted

    assert FranchiseStudioRepo(db, scope).all() == []
    assert _UserScopeRepo(db, scope).all() == []


def test_empty_visibility_sees_nothing(db, two_studios):
    """A user scoped to zero studios must see zero rows. Getting this wrong
    (treating empty as unrestricted) would be the worst possible failure."""
    t = two_studios
    scope = AccessScope(
        user=t["staff_a"],
        operating_studio_id=None,
        visible_studio_ids=frozenset(),
        visible_franchise_id=None,
    )
    assert FranchiseStudioRepo(db, scope).all() == []
    assert _UserScopeRepo(db, scope).all() == []
