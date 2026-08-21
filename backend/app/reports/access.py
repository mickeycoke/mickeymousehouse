"""Franchise -> studio membership lookup used by a couple of access checks
that live outside `app/data/` proper (routes/auth.py's setup-email scope
check, routes/studios.py's access-codes gate).

This is the only survivor of what was originally a much larger reporting
access-control module (client/studio/franchise report permissions) — the
rest was deleted along with the client/session/routine reporting feature it
served. `FranchiseStudio` is a "studio"-scoped model in the data-layer
contract (tests/test_data_layer_contract.py), so this raw read is tracked in
that file's LEGACY_BUDGET rather than routed through a repo — kept as a
single, narrow, reviewable exception rather than growing a new one.
"""
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.models.franchise_studio import FranchiseStudio


def get_franchise_studio_ids_for_reporting(db: DBSession, franchise_id: UUID) -> set[UUID]:
    rows = (
        db.query(FranchiseStudio.studio_id)
        .filter(
            FranchiseStudio.franchise_id == franchise_id,
            FranchiseStudio.is_active == True,
        )
        .all()
    )
    return {row.studio_id for row in rows}
