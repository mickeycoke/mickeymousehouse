"""Franchise <-> studio membership lookups used to build `AccessScope` itself.

This is chicken-and-egg with the rest of `app/data/`: every other repo here
is constructed FROM an `AccessScope` (see `app/data/base.py`), but resolving
an admin's operating studio down to its ONE franchise has to happen WHILE
building that scope, in `app/data/scope.py`'s `get_scope()` — before any
`ScopedRepo` exists to do it. So this is a small, deliberate exception, the
same shape as `app/data/auth_lookup.py`'s pre-auth user lookups: a narrow,
reviewable query outside the repo-class pattern, living in `app/data/` (not
`app/utils/`) specifically so it is exempt from the raw-query AST guard for
the right reason — it IS the data layer, not a route bypassing it.

Do not add anything else here beyond what `get_scope()` needs — this module
is imported BY `app/data/scope.py`, so importing `app/data/base.py` or
`app/data/scope.py` back from here (as an ordinary `ScopedRepo` subclass
would need to) is a circular import at process start. An ordinary,
scope-holding `FranchiseStudio` repo belongs in its own file — see
`app/data/franchise_studio_repo.py`.
"""
from sqlalchemy.orm import Session

from app.models.franchise_studio import FranchiseStudio


def get_franchise_id_for_studio(db: Session, studio_id):
    """The franchise that owns `studio_id`, via an active `FranchiseStudio`
    link, or None if the studio has no franchise (or `studio_id` is falsy).

    This is the franchise-axis counterpart of `operating_studio_id` itself:
    it lets a caller who has already been narrowed to ONE studio (an admin's
    X-Studio-Id selection) be narrowed to that studio's ONE franchise too,
    the same way `get_client_visibility_studio_ids` narrows the studio axis.
    """
    if not studio_id:
        return None
    link = (
        db.query(FranchiseStudio)
        .filter(FranchiseStudio.studio_id == studio_id, FranchiseStudio.is_active == True)
        .first()
    )
    return link.franchise_id if link else None
