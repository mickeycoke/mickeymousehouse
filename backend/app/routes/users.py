from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.dependencies import get_db, get_current_user, get_operating_studio_id
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse, PinResponse, PinUpdate
from app.utils.ownership import get_managed_studio_ids, get_franchise_owner_franchise_id, is_user_in_franchise
from app.utils.password import hash_password, hash_pin

router = APIRouter(prefix="/api/users", tags=["users"])

# Roles a studio owner/manager may hand out. They can never create or touch
# admins, managers, or fellow owners.
SCOPED_ASSIGNABLE_ROLES = {"instructor", "member"}


def _require_user_admin(current_user: User, db: Session, operating_studio_id=None):
    """Admin → None (everything), or the selected operating studio if one is
    set. Studio owner/manager → their studio ids. Anyone else → 403."""
    managed = get_managed_studio_ids(db, current_user, operating_studio_id=operating_studio_id)
    if managed is not None and not managed:
        raise HTTPException(status_code=403, detail="User administration requires admin or a studio owner/manager role")
    return managed


def _require_target_in_scope(target: User, managed, is_admin: bool, current_user_id, detail: str):
    """STUDIO gate applies to everyone `managed` narrows (admin or not) --
    a row outside `managed` is refused, full stop. The ROLE gate
    (SCOPED_ASSIGNABLE_ROLES) is a DIFFERENT rule, written only for non-admin
    studio owners/managers, who may never touch an admin, a manager, or a
    fellow owner -- it does not apply to an admin narrowed to one studio via
    operating_studio_id. That admin is still globally entitled everywhere
    except the studio boundary itself: only WHICH STUDIO they may act in is
    newly restricted, never WHICH ROLES within it (see
    test_studio_isolation_http.py "users by id" section).

    Self-management is exempt from the STUDIO gate for admins: an admin's own
    account is typically NOT assigned to any specific studio (studio_id is
    NULL for a global admin -- the common shape for a seeded admin account,
    not an edge case), so it would never
    match a single operating studio in `managed` and self-edit would 403
    unconditionally the moment ANY operating studio was selected -- exactly
    the capability this whole fix exists to preserve. Matches `get_user`'s
    existing self-read precedent, kept admin-only here (unlike get_user's
    unconditional bypass) so non-admin owner/manager self-service behavior --
    whatever it already was -- is not altered by this fix; it was never part
    of the reported bug."""
    if is_admin and target.id == current_user_id:
        return
    if managed is None:
        return
    if target.studio_id not in managed:
        raise HTTPException(status_code=403, detail=detail)
    if not is_admin and target.role not in SCOPED_ASSIGNABLE_ROLES:
        raise HTTPException(status_code=403, detail=detail)


@router.get("", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    managed = _require_user_admin(current_user, db, operating_studio_id=operating_studio_id)
    q = db.query(User).filter(User.is_active == True)
    if managed is not None:
        # Own-studio people plus yourself
        q = q.filter((User.studio_id.in_(managed)) | (User.id == current_user.id))
    return q.all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    is_admin = current_user.role == "admin"
    managed = None if is_admin else get_managed_studio_ids(db, current_user)
    owned_franchise = None if is_admin else get_franchise_owner_franchise_id(db, current_user)
    studio_id = payload.studio_id
    if not is_admin:
        if managed:  # studio owner/manager: instructors/members in their own studio
            if payload.role not in SCOPED_ASSIGNABLE_ROLES:
                raise HTTPException(status_code=403, detail="Studio owners/managers may only create instructors or members")
            if studio_id is None:
                studio_id = next(iter(managed))
            elif studio_id not in managed:
                raise HTTPException(status_code=403, detail="You can only add people to your own studio")
        elif owned_franchise:  # franchise owner: reporting logins only, no studio attachment
            if payload.role != "member":
                raise HTTPException(status_code=403, detail="Franchise owners may only create reporting (member) accounts")
            studio_id = None
        else:
            raise HTTPException(status_code=403, detail="User administration requires admin, a studio owner/manager, or a franchise owner")
    elif studio_id is None and operating_studio_id is not None:
        # Admin operating within a studio: new people land in THAT studio (so a
        # created instructor shows up there) unless an explicit studio was chosen.
        studio_id = operating_studio_id

    # Only dedup/revive when an email is given — a null email is a PIN-only
    # instructor, and `email == None` would render as IS NULL and wrongly match
    # every other null-email instructor.
    existing = db.query(User).filter(User.email == payload.email).first() if payload.email else None
    if existing and existing.is_active:
        raise HTTPException(status_code=400, detail="Email already registered")
    if existing:
        # "Delete" is a soft delete (is_active=False) — sessions anchor to the
        # user row, so a removed instructor's email would otherwise be locked
        # forever. Re-adding that email revives the SAME account instead of
        # erroring. Non-admins may only revive someone already in their own
        # scope, so they can't capture an email that belongs elsewhere.
        if not is_admin:
            in_scope = (
                (managed and existing.studio_id in managed)
                or (owned_franchise and is_user_in_franchise(db, existing, owned_franchise))
            )
            if not in_scope:
                raise HTTPException(status_code=400, detail="Email already registered")
        existing.name = payload.name
        existing.role = payload.role
        existing.studio_id = studio_id
        existing.password_hash = hash_password(payload.password if payload.password else uuid.uuid4().hex)
        existing.is_active = True
        # Reset onboarding + shared-device state so the revived account is a
        # clean slate: a fresh invite works and no stale PIN carries over.
        existing.invite_sent_at = None
        existing.password_set_at = None
        existing.pin = None
        existing.pin_hash = None
        db.commit()
        db.refresh(existing)
        return existing
    user = User(
        email=payload.email,
        name=payload.name,
        # No password → an unusable hash; they set their own via the setup email.
        password_hash=hash_password(payload.password if payload.password else uuid.uuid4().hex),
        role=payload.role,
        studio_id=studio_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Any login could otherwise read any user's email/role/studio. Allow only:
    # yourself, an unrestricted admin, or staff -- including an admin narrowed
    # via X-Studio-Id, who is scoped exactly like that studio's own owner/
    # manager (CLAUDE.md) -- who administer the target's studio.
    if user.id != current_user.id:
        if current_user.role != "admin":
            managed = get_managed_studio_ids(db, current_user, operating_studio_id=operating_studio_id)
            if not (managed and user.studio_id in managed):
                raise HTTPException(status_code=403, detail="Not authorized")
        elif operating_studio_id and user.studio_id != operating_studio_id:
            # By-id is not exempt from studio scoping: a studio-B user is
            # invisible to an admin operating in studio A, same as it would be
            # to studio A's own staff -- 404, not 403 (CLAUDE.md).
            raise HTTPException(status_code=404, detail="User not found")
    return user


def _email_taken_detail(holder: User, managed) -> str:
    """What the person staring at the edit form has to read to fix it.

    Naming the account that holds the email is the only thing that makes the
    collision actionable — but a studio owner/manager may not see people outside
    their own studios (`get_user`'s rule), so for them a holder elsewhere
    degrades to exactly what `create_user` discloses about a taken email, and
    not one word more.
    """
    if managed is not None and holder.studio_id not in managed:
        return "Email already registered"
    if holder.is_active:
        return (
            f"That email already belongs to another account ({holder.name}). "
            "Use a different email, or change that account's email first."
        )
    # RULING: a soft-deleted holder still blocks. Its email is not
    # abandoned — `create_user` revives that SAME row when the email is added
    # again, because sessions anchor to the user row. Moving the email onto a
    # different row here would quietly strand the removed account's history and
    # is not undoable, so the two paths are kept telling one story: create
    # revives, update refuses.
    return (
        f"That email is still held by a removed account ({holder.name}). "
        "Add that person back to restore their account, or use a different email."
    )


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    managed = _require_user_admin(current_user, db, operating_studio_id=operating_studio_id)

    update_data = payload.model_dump(exclude_unset=True)
    # '' is a real value under users_email_key where NULL is not, so a second
    # blank would collide with the first. EmailStr refuses '' today; this holds
    # the invariant if the schema ever loosens.
    if "email" in update_data and not (update_data["email"] or "").strip():
        update_data["email"] = None
    new_email = update_data.get("email")

    # The target row AND whoever already holds the new email, in one lookup:
    # `User` still has no repository, and this file's raw-read count is frozen
    # by tests/test_data_layer_contract.py — it may shrink, never grow.
    # `== new_email` is deliberately exact; folding case would change which
    # emails collide, and that is a product decision, not part of this fix.
    wanted = User.id == user_id
    if new_email:
        wanted = wanted | (User.email == new_email)
    rows = db.query(User).filter(wanted).all()

    user = next((r for r in rows if r.id == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_target_in_scope(user, managed, current_user.role == "admin", current_user.id,
                             "You can only manage your own studio's instructors")

    if managed is not None:
        if update_data.get("role") and update_data["role"] not in SCOPED_ASSIGNABLE_ROLES:
            raise HTTPException(status_code=403, detail="Studio owners/managers may only assign instructor or member")
        if update_data.get("studio_id") and update_data["studio_id"] not in managed:
            raise HTTPException(status_code=403, detail="You can only move people within your own studios")

    # Re-saving your OWN email matches this row, not a holder — the edit form
    # posts the email back on every save, so that is the common case and must
    # pass untouched. Without the check the unique index fired as an unhandled
    # 500; the password hash rides the same transaction, so it rolled back with
    # it. That was the whole of "setting a password from the administrator does
    # not work".
    holder = next((r for r in rows if r.id != user.id), None) if new_email else None
    if holder:
        raise HTTPException(status_code=400, detail=_email_taken_detail(holder, managed))

    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))
    for field, value in update_data.items():
        setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        # The check above cannot close the window between itself and the commit
        # — a concurrent insert can still take the email. Roll back so the
        # session is not left poisoned for the rest of the request, and answer
        # with the same 400 the guard would have given rather than a 500.
        db.rollback()
        if "users_email_key" not in str(getattr(exc, "orig", exc)):
            raise
        raise HTTPException(status_code=400, detail="Email already registered")
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    managed = _require_user_admin(current_user, db, operating_studio_id=operating_studio_id)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_target_in_scope(user, managed, current_user.role == "admin", current_user.id,
                             "You can only manage your own studio's instructors")
    user.is_active = False
    db.commit()
    return {"message": "User deactivated"}


# ── Shared-device PIN (admin / studio owner-manager) ───────────────────────
def _pin_response(user: User) -> PinResponse:
    return PinResponse(
        user_id=user.id, name=user.name,
        pin=user.pin, has_pin=bool(user.pin or user.pin_hash),
    )


@router.get("/{user_id}/pin", response_model=PinResponse)
def get_user_pin(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    """View one instructor's shared-device PIN. For the studio's owner/manager
    (or an admin) to read and hand out. `pin` is null when none is set, or when
    only a legacy hash exists — reset it to make it viewable."""
    managed = _require_user_admin(current_user, db, operating_studio_id=operating_studio_id)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_target_in_scope(user, managed, current_user.role == "admin", current_user.id,
                             "You can only view your own studio's instructors")
    return _pin_response(user)


@router.put("/{user_id}/pin", response_model=PinResponse)
def set_user_pin(
    user_id: uuid.UUID,
    payload: PinUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: uuid.UUID | None = Depends(get_operating_studio_id),
):
    """Set (4–8 digits) or clear (null) an instructor's shared-device PIN. Writes
    the recoverable plaintext and the login hash together so they never drift."""
    managed = _require_user_admin(current_user, db, operating_studio_id=operating_studio_id)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_target_in_scope(user, managed, current_user.role == "admin", current_user.id,
                             "You can only manage your own studio's instructors")
    if payload.pin is None:
        user.pin = None
        user.pin_hash = None
    else:
        user.pin = payload.pin
        user.pin_hash = hash_pin(payload.pin)
    db.commit()
    db.refresh(user)
    return _pin_response(user)
