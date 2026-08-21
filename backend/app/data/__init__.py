"""Central data access layer.

Every read of a scoped entity goes through a repo in this package. Routes do
NOT call `db.query(User | StudioOwner | FranchiseStudio | ...)` directly for
a model registered "studio"/"franchise"/"derived" in
`tests/test_data_layer_contract.py` — that test, and
`tests/test_no_unscoped_queries.py`'s narrower zero-tolerance gate on the
core tenancy models, fail the build if they do.

Why this exists: a correct helper being merely optional to call is how a
studio-isolation bug gets in — an endpoint that hand-writes its own filter
can always get it wrong, or forget it. The fix is structural rather than
advisory: a repo cannot be built without an AccessScope, and no repo has a
code path that returns an unfiltered query. Scoping is applied by
construction, not by remembering.
"""

from app.data.scope import AccessScope, get_scope
from app.data.base import StudioScopedRepo, FranchiseScopedRepo, DerivedScopeRepo

__all__ = [
    "AccessScope",
    "get_scope",
    "StudioScopedRepo",
    "FranchiseScopedRepo",
    "DerivedScopeRepo",
]
