"""Who can see what, resolved once per request.

This wraps the EXISTING visibility helpers in `app.utils.ownership` rather
than reimplementing them — that logic is correct and well-tested. What was
missing was a single place that every query is forced to consult.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session as DBSession

from app.dependencies import (
    get_db,
    get_current_user,
    get_operating_studio_id,
    STAFF_ROLES,
)
from app.models.user import User
from app.data.franchise_studios import get_franchise_id_for_studio
from app.utils.ownership import (
    get_client_visibility_studio_ids,
    get_user_franchise_id,
)


@dataclass(frozen=True)
class AccessScope:
    """The answer to "which studios/franchises may this request see", computed
    once and handed to every repo the request uses.

    visible_studio_ids:
        None       = unrestricted (admin with no operating studio selected)
        frozenset  = exactly these studios. An EMPTY set means "see nothing",
                     which is a real, deliberate state (e.g. a franchise-level
                     user with no studio attachment) — never widen it.

    visible_franchise_id:
        None       = unrestricted for an admin with no operating studio
                     selected (mirrors visible_studio_ids' None); for a
                     non-admin with no franchise attachment it means "no
                     franchise" and `FranchiseScopedRepo` filters to the
                     shared standards only — it is NEVER "see everything"
                     outside the admin-unrestricted case.
        UUID       = exactly this franchise (plus the NULL shared standards,
                     which are always visible on this axis). Set for a
                     non-admin's own franchise, OR for an admin who has an
                     operating studio selected — resolved from THAT studio,
                     the same way visible_studio_ids narrows to
                     {operating_studio_id} for an admin on the studio axis.
    """

    user: User
    operating_studio_id: Optional[UUID]
    visible_studio_ids: Optional[frozenset]
    visible_franchise_id: Optional[UUID]

    @property
    def is_unrestricted(self) -> bool:
        return self.visible_studio_ids is None

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin"


def get_scope(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
) -> AccessScope:
    """FastAPI dependency. `get_client_visibility_studio_ids` already collapses
    to exactly {operating_studio_id} when one is set (admin-selected studio, or
    the studio baked into an impersonation token), so that precedence rule is
    honored here for free — and identically for every entity."""
    visible = get_client_visibility_studio_ids(
        db, current_user, operating_studio_id=operating_studio_id
    )
    # `None` from that helper means "unrestricted", which it grants to admins
    # AND to staff with no studio attachment (head-office users). A portal
    # login (role="client") has no attachment either, so it would fall into
    # the same branch and see EVERY studio. Non-staff never gets unrestricted
    # visibility — clamp to "see nothing" and let the dedicated portal
    # endpoints grant access through their own per-client checks.
    if visible is None and current_user.role not in STAFF_ROLES:
        visible = set()
    if current_user.role == "admin":
        # Unrestricted (None) unless the admin has an operating studio
        # selected, in which case narrow to THAT studio's ONE franchise —
        # never widen back to None just because the studio has no franchise
        # link (that resolves to None here too, but `FranchiseScopedRepo`
        # tells the two cases apart via `operating_studio_id`, not this
        # field alone; see its `_apply_scope`).
        visible_franchise_id = (
            get_franchise_id_for_studio(db, operating_studio_id)
            if operating_studio_id
            else None
        )
    else:
        visible_franchise_id = get_user_franchise_id(db, current_user)
    return AccessScope(
        user=current_user,
        operating_studio_id=operating_studio_id,
        visible_studio_ids=None if visible is None else frozenset(visible),
        visible_franchise_id=visible_franchise_id,
    )
