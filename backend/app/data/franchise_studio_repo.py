"""`FranchiseStudio` reads for callers that already hold an `AccessScope`.

Split out from `app/data/franchise_studios.py` on purpose: that module is
imported BY `app/data/scope.py` (to resolve an admin's operating studio down
to its franchise while the scope itself is still being built), so it must
never import `app/data/scope.py` or `app/data/base.py` back — either import
would be a circular import at process start (`scope.py` -> `franchise_studios
.py` -> `base.py`/`scope.py`, mid-init, `AccessScope` not yet defined). This
file has no such constraint: everything here runs AFTER a scope already
exists, the normal `ScopedRepo` shape every other repo in this package uses.

Added for the admin billing-by-franchise filter:
`GET /api/admin/billing/studios` is admin-only and already unrestricted (no
operating studio selected -> `.query()` sees every active link, same as the
raw `Studio` read that route already does — see its docstring), so this
behaves like a plain global lookup there while still honoring the studio axis
if an admin HAS narrowed to one operating studio ("X-Studio-Id binds admins
too").
"""
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session as DBSession

from app.data.base import StudioScopedRepo
from app.data.scope import AccessScope, get_scope
from app.dependencies import get_db
from app.models.franchise_studio import FranchiseStudio


class FranchiseStudioRepo(StudioScopedRepo):
    model = FranchiseStudio

    def list_studio_ids_for_franchise(self, franchise_id: UUID) -> set:
        """Every studio id with an ACTIVE link to `franchise_id`, honoring
        this caller's studio-axis scope first (`.query()`), same as any other
        `StudioScopedRepo` read. An unknown/nonexistent franchise_id simply
        yields an empty set, not an error — same "no validation on an
        optional filter" convention as `GET /api/franchise-studios`."""
        rows = (
            self.query()
            .filter(FranchiseStudio.franchise_id == franchise_id, FranchiseStudio.is_active == True)
            .with_entities(FranchiseStudio.studio_id)
            .all()
        )
        return {row[0] for row in rows}


def franchise_studio_repo(
    db: DBSession = Depends(get_db), scope: AccessScope = Depends(get_scope)
) -> FranchiseStudioRepo:
    return FranchiseStudioRepo(db, scope)
