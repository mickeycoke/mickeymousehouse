"""Repo base classes — one per scoping axis.

Three axes exist in this app, and conflating them is exactly how the current
bugs happened:

  1. STUDIO   (`studio_id` column) — clients, exercises, routines, machines.
     A NULL studio_id row is INVISIBLE. No fallback, no exceptions.
     The one exception is machines, where NULL is a deliberate shared
     catalog — that repo opts in explicitly via `shared_rows_visible`.

  2. FRANCHISE (`franchise_id` column) — custom metric definitions.
     Here NULL DOES mean "shared standard, visible to everyone".
     Deliberately the opposite of the studio axis.

  3. DERIVED (no scope column) — routine_exercises, session results, machine
     settings, etc. Only safe when reached through their parent, so these
     enforce the parent join rather than trusting the caller.

No class here has a code path that returns an unfiltered query.
"""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.data.scope import AccessScope


class ScopedRepo:
    """Cannot be constructed without a scope. Subclasses must implement
    `query()` such that it is always filtered."""

    model = None
    not_found_detail = "Not found"

    def __init__(self, db: DBSession, scope: AccessScope):
        if self.model is None:
            raise TypeError(f"{type(self).__name__} must set `model`")
        self.db = db
        self.scope = scope

    def query(self):
        raise NotImplementedError

    def all(self):
        return self.query().all()

    def get(self, id_):
        return self.query().filter(self.model.id == id_).first()

    def get_or_404(self, id_):
        """404 rather than 403 for out-of-scope ids: whether a record exists in
        another studio is itself information this caller is not entitled to."""
        row = self.get(id_)
        if row is None:
            raise HTTPException(status_code=404, detail=self.not_found_detail)
        return row


class StudioScopedRepo(ScopedRepo):
    """Entities owning a `studio_id`."""

    # Only MachineRepo sets this True — NULL there means "shared catalog".
    # Everywhere else a NULL studio_id row is invisible, per owner policy.
    shared_rows_visible = False

    def _apply_scope(self, q, studio_ids: Optional[frozenset] = None):
        ids = self.scope.visible_studio_ids if studio_ids is None else studio_ids
        if ids is None:
            return q  # admin, no operating studio selected
        col = self.model.studio_id
        if not ids:
            # Deliberate "see nothing" (e.g. franchise-level user with no
            # studio). Expressed explicitly so it can't be mistaken for
            # "unscoped" and so SQLAlchemy doesn't warn on an empty IN.
            return q.filter(False)
        if self.shared_rows_visible:
            return q.filter(or_(col.in_(ids), col.is_(None)))
        return q.filter(col.in_(ids))

    def query(self):
        return self._apply_scope(self.db.query(self.model))

    ambiguous_studio_detail = (
        "You work at multiple studios — pick which studio this belongs to."
    )

    def stamp_new(self, **kwargs):
        """Build a new row already stamped with the right studio.

        Replaces the near-identical private copies that had accumulated
        (e.g. `_new_exercise_studio_id`). An explicit studio_id in kwargs is
        honored only if the caller may actually see that studio.

        Refuses to produce a row the CALLER would not be able to see. A
        multi-studio manager with no operating studio selected used to get
        studio_id=None here, and since NULL is invisible the record vanished
        the moment it was saved — a 201 followed by silent data loss. Make
        them choose instead, the same 422 `clients_setup.create_client`
        already raises.

        Deliberately narrow. It does NOT fire when:
          * the caller is unrestricted (an admin sees NULL rows, so nothing
            disappears on them, and they can assign a studio later);
          * NULL is a legitimate state for the entity (`shared_rows_visible`);
          * the row is reachable by another path — see
            `_reachable_without_studio`, which is how a client-owned routine
            stays creatable: it is visible through its client's studio.
        """
        studio_id = kwargs.pop("studio_id", None)
        if studio_id is None:
            studio_id = self.default_new_studio_id()
            if (
                studio_id is None
                and not self.shared_rows_visible
                and not self.scope.is_unrestricted
                and not self._reachable_without_studio(kwargs)
            ):
                raise HTTPException(
                    status_code=422, detail=self.ambiguous_studio_detail
                )
        elif not self.scope.is_unrestricted:
            visible = self.scope.visible_studio_ids or frozenset()
            if studio_id not in visible:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot create records in another studio",
                )
        return self.model(studio_id=studio_id, **kwargs)

    def _reachable_without_studio(self, kwargs) -> bool:
        """Can a new row with no studio_id still be seen by this caller?

        False for most entities — no studio means invisible. Overridden where
        the entity has a second ownership path (see RoutineRepo, where a
        client_id makes the routine visible through that client's studio).
        """
        return False

    def default_new_studio_id(self) -> Optional[UUID]:
        """Operating studio if one is selected; else the caller's single
        studio when unambiguous; else None."""
        if self.scope.operating_studio_id:
            return self.scope.operating_studio_id
        visible = self.scope.visible_studio_ids
        if visible and len(visible) == 1:
            return next(iter(visible))
        return None


class FranchiseScopedRepo(ScopedRepo):
    """Entities owning a `franchise_id`, where NULL = shared standard.

    This NULL rule is intentional and NOT the studio rule — see module
    docstring.
    """

    def _apply_scope(self, q):
        # Unrestricted ONLY for an admin with no operating studio selected —
        # `visible_franchise_id` alone can't carry that distinction, because
        # it is also None when an admin's SELECTED studio simply has no
        # franchise link (a real, narrower state, not "see everything"). So
        # this checks `operating_studio_id`, the same signal StudioScopedRepo
        # effectively uses via visible_studio_ids being None only when no
        # operating studio is set. Once an operating studio is selected, an
        # admin is narrowed exactly like that studio's own staff — "X-Studio-Id
        # binds admins too" (CLAUDE.md) — even down to "no franchise, so only
        # the shared standards."
        if self.scope.is_admin and self.scope.operating_studio_id is None:
            return q
        col = self.model.franchise_id
        return q.filter(or_(col == self.scope.visible_franchise_id, col.is_(None)))

    def query(self):
        return self._apply_scope(self.db.query(self.model))


class DerivedScopeRepo(ScopedRepo):
    """Entities with no scope column of their own.

    These are the subtlest leaks: query `RoutineExercise` directly and you've
    bypassed the routine's studio check with nothing to warn you. So the
    parent join is enforced here rather than left to the caller.
    """

    parent_repo_cls = None   # e.g. RoutineRepo
    parent_fk = None         # column on this model holding the parent id

    def query(self):
        if self.parent_repo_cls is None or self.parent_fk is None:
            raise TypeError(
                f"{type(self).__name__} must set `parent_repo_cls` and `parent_fk`"
            )
        parent = self.parent_repo_cls(self.db, self.scope)
        visible_parent_ids = parent.query().with_entities(parent.model.id).scalar_subquery()
        return self.db.query(self.model).filter(
            getattr(self.model, self.parent_fk).in_(visible_parent_ids)
        )
