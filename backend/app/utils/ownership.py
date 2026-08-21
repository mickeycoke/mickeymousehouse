from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.franchise_owner import FranchiseOwner
from app.models.franchise_studio import FranchiseStudio
from app.models.studio_owner import StudioOwner
from app.models.user import User


@dataclass(frozen=True)
class OwnershipScope:
    is_admin: bool
    studio_ids: set[UUID] = field(default_factory=set)
    franchise_ids: set[UUID] = field(default_factory=set)
    # OWNER-level-only subsets (excludes manager) -- computed for free from
    # the same StudioOwner/FranchiseOwner rows already loaded below, so a
    # level-specific caller (e.g. the self-serve billing tab, owner-only)
    # never needs its own raw query. See get_owned_billing_studio_ids.
    owner_level_studio_ids: set[UUID] = field(default_factory=set)
    owner_level_franchise_ids: set[UUID] = field(default_factory=set)


def can_manage_ownership(user: User) -> bool:
    return user.role == "admin"


def get_user_ownership_scope(db: Session, user: User) -> OwnershipScope:
    """Franchise and studio are SEPARATE tiers.

    - studio_ids: studios the user operates at the STUDIO level (they are a
      studio owner/manager). This is studio-level operational access — clients,
      sessions, dashboards, the studio list.
    - franchise_ids: franchises the user holds a franchise-LEVEL role in
      (owner/manager). Franchise roles manage the franchise, NOT its studios,
      so a franchise role does NOT grant studio-level access to the franchise's
      studios. Franchise-level reporting resolves its studios from franchise_ids
      independently; it never needs studio_ids.

    A franchise owner is NOT a studio owner — the two are never conflated here.
    """
    if user.role == "admin":
        return OwnershipScope(is_admin=True)

    studio_owner_rows = (
        db.query(StudioOwner)
        .filter(StudioOwner.user_id == user.id, StudioOwner.is_active == True)
        .all()
    )
    studio_ids = {row.studio_id for row in studio_owner_rows}
    owner_level_studio_ids = {row.studio_id for row in studio_owner_rows if row.level == "owner"}

    franchise_owner_rows = (
        db.query(FranchiseOwner)
        .filter(FranchiseOwner.user_id == user.id, FranchiseOwner.is_active == True)
        .all()
    )
    franchise_ids = {row.franchise_id for row in franchise_owner_rows}
    owner_level_franchise_ids = {row.franchise_id for row in franchise_owner_rows if row.level == "owner"}

    return OwnershipScope(
        is_admin=False,
        studio_ids=studio_ids,
        franchise_ids=franchise_ids,
        owner_level_studio_ids=owner_level_studio_ids,
        owner_level_franchise_ids=owner_level_franchise_ids,
    )


def get_instructor_studio_ids(db: Session, user: User) -> set:
    """The studios this user teaches at — active `user_studios` memberships. The
    Phase-3 backfill seeded the primary studio as a membership, so this is a
    superset of the legacy `user.studio_id` for existing users."""
    from app.models.user_studio import UserStudio
    return {
        row.studio_id
        for row in db.query(UserStudio.studio_id)
        .filter(UserStudio.user_id == user.id, UserStudio.is_active == True)
        .all()
    }


def can_view_studio(db: Session, user: User, studio_id: UUID) -> bool:
    scope = get_user_ownership_scope(db, user)
    return scope.is_admin or studio_id in scope.studio_ids


def can_view_franchise(db: Session, user: User, franchise_id: UUID) -> bool:
    scope = get_user_ownership_scope(db, user)
    return scope.is_admin or franchise_id in scope.franchise_ids


def _studio_ids_for_franchises(db: Session, franchise_ids) -> set:
    """Studios belonging to any of the given franchises (via FranchiseStudio).
    Shared by `get_client_visibility_studio_ids`'s franchise-closure
    expansion and `get_owned_billing_studio_ids`'s franchise-owner
    expansion -- kept as ONE query call site so both stay under this file's
    legacy raw-query budget instead of each carrying its own (CLAUDE.md: fix
    the code, never grow the budget)."""
    if not franchise_ids:
        return set()
    return {
        row.studio_id
        for row in db.query(FranchiseStudio)
        .filter(FranchiseStudio.franchise_id.in_(franchise_ids), FranchiseStudio.is_active == True)
        .all()
    }


def get_client_visibility_studio_ids(db: Session, user: User, include_franchise: bool = False,
                                     operating_studio_id=None):
    """Which studios' clients may this user see? (A studio must only see
    their OWN clients.)

    Returns None for "all clients" (admins, and staff not attached to any
    studio — e.g. head-office users), otherwise the set of studio ids from
    the user's home studio plus any owned studios/franchises.

    operating_studio_id: the studio the caller is operating within — an admin's
    selected studio, OR the studio baked into an impersonation token. It is
    authoritative: when set it narrows visibility to that one studio for ANYONE,
    which is what keeps an impersonated (non-admin) instructor scoped to the
    studio the admin picked rather than falling back to their own visibility.
    """
    if operating_studio_id:
        return {operating_studio_id}
    if user.role == "admin":
        return None
    scope = get_user_ownership_scope(db, user)
    studio_ids = set(scope.studio_ids)
    studio_ids |= get_instructor_studio_ids(db, user)   # studios they teach at
    if user.studio_id:
        studio_ids.add(user.studio_id)
    if not studio_ids:
        # A franchise-level user (franchise role, no studio attachment) is NOT
        # head-office-all-access — franchise roles get NO studio client data.
        # Return an empty set (see nothing), never None (which means "all
        # clients"). Only genuinely unscoped staff fall through to None.
        if scope.franchise_ids:
            return set()
        return None
    if not include_franchise:
        # Default: a studio sees its OWN clients. Franchise-wide search is
        # opt-in at session start.
        return studio_ids

    # Franchise closure: clients belong to the FRANCHISE and may train at
    # any of its studios — expand to every studio in the same franchises.
    franchise_ids = {
        row.franchise_id
        for row in db.query(FranchiseStudio)
        .filter(FranchiseStudio.studio_id.in_(studio_ids), FranchiseStudio.is_active == True)
        .all()
    }
    if franchise_ids:
        studio_ids |= _studio_ids_for_franchises(db, franchise_ids)
    return studio_ids


def get_managed_studio_ids(db: Session, user: User, operating_studio_id=None):
    """Studios whose PEOPLE this user may administer (create/edit
    instructors). None = all (admin); empty set = no user administration.
    Only an active studio_owners row (level owner OR manager) grants this —
    per the role model, owners and managers set up instructors.

    operating_studio_id: the studio the caller is operating within (an admin's
    selection or an impersonation token's studio).

    THE HEADER NARROWS. IT DOES NOT GRANT.

    This used to `return {operating_studio_id}` for ANY caller, treating the
    header as authoritative — which for a non-admin turned it into a grant. The
    escalation was reproduced end to end: a franchise-A manager who
    also holds a staff attachment at a studio in franchise B (an instructor
    membership, a StudioOwner row, or just `user.studio_id`) passes
    `dependencies.get_operating_studio_id`, which accepts the header for anything
    in ownership scope OR instructor memberships OR the primary studio. That
    caller then arrived here, got `{studio_B}` back, and could administer
    franchise B's people: read its owner roster with emails, flip `is_active` to
    lock a legitimate owner out, and POST a new owner assignment (201).

    So the header is authoritative only for an admin, who is already globally
    entitled and can only ever be narrowing. For everyone else it is intersected
    with what they actually manage: naming a studio you do not manage now yields
    an empty set, and naming one you do manage behaves exactly as before.
    """
    if user.role == "admin":
        # Already entitled everywhere; the header is a deliberate narrowing.
        return {operating_studio_id} if operating_studio_id else None
    rows = (
        db.query(StudioOwner)
        .filter(StudioOwner.user_id == user.id, StudioOwner.is_active == True)
        .all()
    )
    managed = {row.studio_id for row in rows}
    if operating_studio_id:
        return managed & {operating_studio_id}
    return managed


def get_owned_billing_studio_ids(db: Session, user: User) -> set[UUID]:
    """Studios this user may view/manage BILLING for (self-serve owner
    Billing tab). Deliberately different from every other helper here in two
    ways:

    1. OWNER level only, never manager — billing is a financial decision,
       so "owners only".
    2. A franchise owner's studios ARE included, via `FranchiseStudio` —
       even though "franchise and studio are separate tiers" everywhere
       else in this file. Franchise owners can see and manage billing for
       their franchise's studios too, so this is a deliberate, scoped
       exception for this one feature, not a change to the general rule.

    Admins get an empty set: they use the separate, central
    `/api/admin/billing/...` roster, not this self-serve surface.

    Adds NO new raw queries of its own: reuses `get_user_ownership_scope`'s
    already-loaded StudioOwner/FranchiseOwner rows (via its owner-level
    subsets) and the shared `_studio_ids_for_franchises` helper, so this
    file's legacy raw-query budget (CLAUDE.md) doesn't grow.
    """
    if user.role == "admin":
        return set()
    scope = get_user_ownership_scope(db, user)
    return scope.owner_level_studio_ids | _studio_ids_for_franchises(db, scope.owner_level_franchise_ids)


def get_owned_franchise_id(db: Session, user: User):
    """The franchise this user has ANY active FranchiseOwner row on (owner,
    reports, or manager), else None. Used to scope the reporting VIEW — both
    owners and reports-only users see their own franchise's report."""
    row = (
        db.query(FranchiseOwner)
        .filter(FranchiseOwner.user_id == user.id, FranchiseOwner.is_active == True)
        .first()
    )
    return row.franchise_id if row else None


def get_franchise_owner_franchise_id(db: Session, user: User):
    """The franchise this user is a franchise OWNER of (level 'owner'), else None.
    Only owners may add/invite reporting users — reports-only users cannot."""
    row = (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == user.id,
            FranchiseOwner.is_active == True,
            FranchiseOwner.level == "owner",
        )
        .first()
    )
    return row.franchise_id if row else None


def is_user_in_franchise(db: Session, user: User, franchise_id: UUID) -> bool:
    """True if `user` belongs to `franchise_id` — either directly (an active
    FranchiseOwner row) or via their home studio's active franchise link."""
    if (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == user.id,
            FranchiseOwner.franchise_id == franchise_id,
            FranchiseOwner.is_active == True,
        )
        .first()
    ):
        return True
    studio_ids = get_instructor_studio_ids(db, user)
    if user.studio_id:
        studio_ids.add(user.studio_id)
    if studio_ids:
        return (
            db.query(FranchiseStudio)
            .filter(
                FranchiseStudio.studio_id.in_(studio_ids),
                FranchiseStudio.franchise_id == franchise_id,
                FranchiseStudio.is_active == True,
            )
            .first()
            is not None
        )
    return False


def get_user_franchise_id(db: Session, user: User):
    """The ONE franchise this user belongs to (one per user).
    Resolution: franchise role, else home/owned studio's franchise. None = no
    franchise (or admin)."""
    row = (
        db.query(FranchiseOwner)
        .filter(FranchiseOwner.user_id == user.id, FranchiseOwner.is_active == True)
        .first()
    )
    if row:
        return row.franchise_id
    studio_id = user.studio_id
    if not studio_id:
        so = (
            db.query(StudioOwner)
            .filter(StudioOwner.user_id == user.id, StudioOwner.is_active == True)
            .first()
        )
        studio_id = so.studio_id if so else None
    if not studio_id:
        return None
    link = (
        db.query(FranchiseStudio)
        .filter(FranchiseStudio.studio_id == studio_id, FranchiseStudio.is_active == True)
        .first()
    )
    return link.franchise_id if link else None
