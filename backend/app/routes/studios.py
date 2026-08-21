import logging
import secrets
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.data.pricing_tiers import PricingTierRepo
from app.dependencies import (
    get_db, get_current_user, get_managed_franchise_id, get_operating_studio_id,
    require_admin, require_franchise_management,
)
from app.models.franchise_studio import FranchiseStudio
from app.models.pricing_tier import PricingTier
from app.models.studio import Studio
from app.models.user import User
from app.reports.access import get_franchise_studio_ids_for_reporting
from app.schemas.studio import StudioCreate, StudioResponse, StudioUpdate
from app.services import email as email_service
from app.services.email import APP_BASE_URL
from app.services.qr import qr_png_base64
from app.utils.ownership import get_user_ownership_scope, get_managed_studio_ids, get_instructor_studio_ids

logger = logging.getLogger("app.studios")

router = APIRouter(prefix="/api/studios", tags=["studios"])

# Short self-serve onboarding code (Phase 1a). Excludes visually ambiguous
# characters (0/O, 1/I) so staff can read a code off a screen without confusion
# — still an A-Z0-9 subset backed by the unique ix_studios_onboard_code index.
ONBOARD_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ONBOARD_CODE_LENGTH = 6


def ensure_unique_onboard_code(db: Session, length: int = ONBOARD_CODE_LENGTH) -> str:
    """Return a random onboard code not already used by any studio. Relies on
    the caller flushing between allocations when assigning several in a loop so
    each new code sees the previous ones."""
    for _ in range(50):
        code = "".join(secrets.choice(ONBOARD_CODE_ALPHABET) for _ in range(length))
        if not db.query(Studio.id).filter(Studio.onboard_code == code).first():
            return code
    raise HTTPException(status_code=500, detail="Could not allocate a studio onboard code")


def visible_studio_ids(db: Session, user: User) -> set[UUID]:
    scope = get_user_ownership_scope(db, user)
    if scope.is_admin:
        return set()

    studio_ids = set(scope.studio_ids)
    studio_ids |= get_instructor_studio_ids(db, user)
    if user.studio_id:
        studio_ids.add(user.studio_id)
    return studio_ids


def _franchise_ids_for(db: Session, studio_ids: list[UUID]) -> dict[UUID, UUID]:
    """studio_id -> its active franchise_id (only for studios that have one)."""
    if not studio_ids:
        return {}
    rows = db.query(FranchiseStudio.studio_id, FranchiseStudio.franchise_id).filter(
        FranchiseStudio.studio_id.in_(studio_ids),
        FranchiseStudio.is_active == True,
    ).all()
    return {studio_id: franchise_id for studio_id, franchise_id in rows}


def _attach_franchise(db: Session, studios: list[Studio]) -> list[Studio]:
    """Set a transient .franchise_id on each studio for the response."""
    mapping = _franchise_ids_for(db, [s.id for s in studios])
    for s in studios:
        s.franchise_id = mapping.get(s.id)
    return studios


def _set_studio_franchise(db: Session, studio_id: UUID, franchise_id, assigned_by: UUID):
    """Make franchise_id the studio's sole active franchise (None unassigns)."""
    active_links = db.query(FranchiseStudio).filter(
        FranchiseStudio.studio_id == studio_id,
        FranchiseStudio.is_active == True,
    ).all()
    for link in active_links:
        if link.franchise_id != franchise_id:
            link.is_active = False
    if franchise_id is None:
        return
    if any(link.franchise_id == franchise_id for link in active_links):
        return  # already the active franchise
    existing = db.query(FranchiseStudio).filter(
        FranchiseStudio.studio_id == studio_id,
        FranchiseStudio.franchise_id == franchise_id,
    ).first()
    if existing:
        existing.is_active = True
    else:
        db.add(FranchiseStudio(franchise_id=franchise_id, studio_id=studio_id,
                               assigned_by_user_id=assigned_by, is_active=True))


@router.get("", response_model=List[StudioResponse])
def list_studios(
    include_inactive: bool = False,
    franchise_id: UUID | None = None,
    all_studios: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: UUID | None = Depends(get_operating_studio_id),
):
    scope = get_user_ownership_scope(db, current_user)
    query = db.query(Studio)

    if franchise_id:
        from app.models.franchise_studio import FranchiseStudio
        query = query.join(FranchiseStudio, FranchiseStudio.studio_id == Studio.id).filter(
            FranchiseStudio.franchise_id == franchise_id,
            FranchiseStudio.is_active == True,
        )

    if not scope.is_admin:
        studio_ids = visible_studio_ids(db, current_user)
        if not studio_ids:
            return []
        query = query.filter(Studio.id.in_(studio_ids))
        include_inactive = False
    elif operating_studio_id and not all_studios:
        # Admin scoped to an operating studio: every studio dropdown must show
        # ONLY that studio. The studio switcher (StudiosPage) passes
        # all_studios=true to bypass this so you can still change scope.
        query = query.filter(Studio.id == operating_studio_id)

    if not include_inactive:
        query = query.filter(Studio.is_active == True)

    return _attach_franchise(db, query.order_by(Studio.name).all())


@router.get("/{studio_id}", response_model=StudioResponse)
def get_studio(
    studio_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Studio).filter(Studio.id == studio_id)
    scope = get_user_ownership_scope(db, current_user)

    if not scope.is_admin:
        studio_ids = visible_studio_ids(db, current_user)
        if studio_id not in studio_ids:
            raise HTTPException(status_code=403, detail="Studio is outside your ownership scope")
        query = query.filter(Studio.is_active == True)

    studio = query.first()
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")
    return _attach_franchise(db, [studio])[0]


def _studio_in_managed_franchise(studio_id, franchise_id, db) -> bool:
    return db.query(FranchiseStudio).filter(
        FranchiseStudio.studio_id == studio_id,
        FranchiseStudio.franchise_id == franchise_id,
        FranchiseStudio.is_active == True,
    ).first() is not None


@router.post("", response_model=StudioResponse, status_code=201)
def create_studio(
    payload: StudioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
):
    data = payload.model_dump()
    requested_franchise = data.pop("franchise_id", None)
    studio = Studio(**data)
    # Every new studio gets a self-serve onboarding code up front (Phase 1a).
    studio.onboard_code = ensure_unique_onboard_code(db)
    db.add(studio)
    db.flush()
    # A franchise manager's new studio belongs to THEIR franchise; an admin
    # places it in whichever franchise they picked (may be none).
    managed = get_managed_franchise_id(db, current_user)
    target_franchise = requested_franchise if managed == "ALL" else managed
    if target_franchise is not None:
        _set_studio_franchise(db, studio.id, target_franchise, current_user.id)
    db.commit()
    db.refresh(studio)
    return _attach_franchise(db, [studio])[0]


@router.post("/backfill-onboard-codes")
def backfill_onboard_codes(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Assign onboard codes to any existing studios that lack one. Idempotent —
    studios that already have a code are untouched — so it is safe to re-run."""
    studios = db.query(Studio).filter(Studio.onboard_code.is_(None)).all()
    assigned = 0
    for studio in studios:
        studio.onboard_code = ensure_unique_onboard_code(db)
        db.flush()  # make the new code visible to the next uniqueness check
        assigned += 1
    db.commit()
    return {"assigned": assigned, "remaining_without_code": 0}


@router.get("/{studio_id}/access-codes")
def studio_access_codes(
    studio_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: UUID | None = Depends(get_operating_studio_id),
):
    """Onboarding + shared-device links and QR codes for a studio, for its owner/
    manager (or an admin / the franchise's manager) to give to instructors and to
    set up the front-desk tablet. The URLs pre-fill the studio so a scan lands
    straight on the name list."""
    managed = get_managed_studio_ids(db, current_user, operating_studio_id=operating_studio_id)
    allowed = managed is None or studio_id in managed  # admin or studio owner/manager
    if not allowed:
        fid = get_managed_franchise_id(db, current_user)
        allowed = bool(fid and fid != "ALL" and studio_id in get_franchise_studio_ids_for_reporting(db, fid))
    if not allowed:
        raise HTTPException(status_code=403, detail="You do not manage this studio")

    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")
    code = studio.short_name or studio.onboard_code
    if not code:
        raise HTTPException(status_code=400, detail="This studio has no onboarding code yet.")

    onboard_url = f"{APP_BASE_URL}/onboard?studio={code}"
    shared_url = f"{APP_BASE_URL}/shared?studio={code}"
    return {
        "studio_id": str(studio.id),
        "studio_name": studio.display_name or studio.name,
        "studio_code": code,
        "onboard": {"url": onboard_url, "qr": qr_png_base64(onboard_url)},
        "shared": {"url": shared_url, "qr": qr_png_base64(shared_url)},
    }


def _tier_name_display(tier: Optional[PricingTier]) -> str:
    return tier.name if tier is not None else "no tier"


def _tier_price_display(tier: Optional[PricingTier]) -> str:
    """Formatted for the change-notification email. No tier -> "no tier";
    a real tier with a null price (Enterprise, negotiated) -> "custom";
    otherwise dollars, computed from monthly_price_cents (there is no
    existing dollars-formatting helper in schemas/pricing_tier.py to reuse —
    that module only computes the per-client rate)."""
    if tier is None:
        return "no tier"
    if tier.monthly_price_cents is None:
        return "custom"
    return f"${tier.monthly_price_cents / 100:.2f}"


def _notify_pricing_tier_changed(
    db: Session, studio: Studio, old_tier_id: Optional[UUID], new_tier_id: Optional[UUID],
) -> None:
    """Send the tier-change notification for an already-committed studio
    update. Never raises — a send failure (missing contact_email, or a
    provider error) is logged and swallowed so it can't undo or fail a save
    that has already succeeded."""
    if not studio.contact_email:
        logger.warning(
            "Studio %s pricing tier changed (%s -> %s) but has no contact_email; "
            "skipping notification email.", studio.id, old_tier_id, new_tier_id,
        )
        return

    tier_repo = PricingTierRepo(db)
    old_tier = tier_repo.get(old_tier_id) if old_tier_id else None
    new_tier = tier_repo.get(new_tier_id) if new_tier_id else None

    try:
        email_service.send_pricing_tier_changed_email(
            studio.contact_email,
            studio.display_name or studio.name,
            _tier_name_display(old_tier),
            _tier_name_display(new_tier),
            _tier_price_display(new_tier),
        )
    except Exception as exc:  # noqa: BLE001 — a send failure must not undo the save
        failure = email_service.describe_send_failure(exc)
        logger.error(
            "pricing tier change email FAILED for studio %s (%s): %s",
            studio.id, studio.contact_email, failure,
        )


@router.put("/{studio_id}", response_model=StudioResponse)
def update_studio(
    studio_id: UUID,
    payload: StudioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_franchise_management),
):
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")
    managed = get_managed_franchise_id(db, current_user)
    if managed != "ALL" and not _studio_in_managed_franchise(studio_id, managed, db):
        raise HTTPException(status_code=403, detail="This studio is not in your franchise")
    data = payload.model_dump(exclude_unset=True)
    reassign_franchise = "franchise_id" in data
    new_franchise = data.pop("franchise_id", None)
    # Pricing-tier assignment: capture the OLD value before
    # applying the update below, and whether the field was sent at all
    # (exclude_unset — same "was this field actually sent" convention as
    # franchise_id above), so a same-value re-save or an untouched field
    # never triggers a notification, only a genuine change does.
    tier_field_included = "pricing_tier_id" in data
    old_pricing_tier_id = studio.pricing_tier_id
    new_pricing_tier_id = data.get("pricing_tier_id") if tier_field_included else old_pricing_tier_id
    for field, value in data.items():
        setattr(studio, field, value)
    # Only admins move a studio between franchises; managers can't reassign.
    if reassign_franchise and managed == "ALL":
        _set_studio_franchise(db, studio.id, new_franchise, current_user.id)
    db.commit()
    db.refresh(studio)
    # Only AFTER the row is successfully saved, and only on a genuine change
    # (first assignment, a swap to a different tier, or clearing it) — never
    # on a same-value re-save or when the field wasn't sent at all.
    if tier_field_included and new_pricing_tier_id != old_pricing_tier_id:
        _notify_pricing_tier_changed(db, studio, old_pricing_tier_id, new_pricing_tier_id)
    return _attach_franchise(db, [studio])[0]
