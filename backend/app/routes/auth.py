import logging
import os
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from uuid import UUID

from typing import Optional

from app.dependencies import (
    get_db, get_current_user, require_admin, get_operating_studio_id,
    get_managed_franchise_id,
)
from app.models.studio import Studio
from app.models.user import User
from app.reports.access import get_franchise_studio_ids_for_reporting
from app.schemas.onboard import (
    InstructorLite, SharedLoginRequest, StudioLite,
    StudioLookupRequest, StudioLookupResponse,
)
from app.schemas.user import (
    LoginRequest, LoginResponse, UserResponse,
    InviteRequest, InviteResponse, InviteInfoResponse, SetPasswordRequest,
    SetupLinkResponse, ChangePasswordRequest,
    ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordInfoResponse,
    ResetPasswordRequest,
)
from app.data.auth_lookup import get_active_user_by_email, get_active_user_by_id
from app.services import email as email_service
from app.services.login_audit import record_login_event
from app.utils.ownership import get_managed_studio_ids, get_franchise_owner_franchise_id, is_user_in_franchise
from app.utils.password import verify_password, hash_password, normalize_pin
from app.utils.studio_lookup import resolve_studio_by_code
from app.utils.tokens import (
    ALGORITHM, INVITE_EXPIRE_HOURS, SECRET, create_access_token, create_invite_token,
    decode_invite_token, create_reset_token, decode_reset_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Same naming convention as app/services/email.py ("app.email") and
# app/main.py ("app.main") so a prod log grep can select by feature.
logger = logging.getLogger("app.auth")

# Shared front-desk-device sessions are deliberately short-lived (the tablet
# logs in to ALL of a studio's clients). Studio-scoped + short-expiry per the
# rollout security note.
SHARED_SESSION_EXPIRE_MINUTES = int(os.getenv("SHARED_SESSION_EXPIRE_MINUTES", "60"))
MAX_SHARED_INSTRUCTORS = 500
# A fixed hash to verify against when no real user/PIN matched, so a failed
# shared login costs the same bcrypt work as a real one and can't be timed to
# enumerate valid studios/instructors.
_DUMMY_PIN_HASH = hash_password("shared-device-dummy-pin-value")
_SHARED_LOGIN_FAILED = "Incorrect studio code, name, or PIN."


def _mint_shared_session_token(user: User, studio_id) -> str:
    """A short-lived, studio-SCOPED access token for a shared device.

    Mirrors create_access_token's claim shape exactly (type='access', sub, role,
    osid) so get_current_user and get_operating_studio_id treat it identically —
    but with a deliberately short expiry, which create_access_token can't express
    without changing utils/tokens.py. Reuses that module's SECRET/ALGORITHM;
    tokens.py itself is untouched.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "type": "access",
        "osid": str(studio_id),
        "exp": now + timedelta(minutes=SHARED_SESSION_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def _load_invited_user(db: Session, token: str) -> User:
    """Decode an invite token and return its (valid, active) user, or raise 400.
    Enforces single use: a token issued before the user last set a password
    is dead."""
    try:
        payload = decode_invite_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="This link has expired. Ask for a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="This link is not valid.")

    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=400, detail="This link is not valid.")

    issued = datetime.utcfromtimestamp(payload["iat"])
    if user.password_set_at and issued < user.password_set_at:
        raise HTTPException(status_code=400, detail="This link has already been used.")
    return user


def _load_reset_user(db: Session, token: str) -> User:
    """Decode a reset token and return its (valid, active) user, or raise 400.
    Enforces single use: a token issued before the user last set a password
    is dead. Mirrors _load_invited_user exactly, for the reset-token type."""
    try:
        payload = decode_reset_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="This link has expired. Ask for a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="This link is not valid.")

    user = get_active_user_by_id(db, payload["sub"])
    if not user:
        raise HTTPException(status_code=400, detail="This link is not valid.")

    issued = datetime.utcfromtimestamp(payload["iat"])
    if user.password_set_at and issued < user.password_set_at:
        raise HTTPException(status_code=400, detail="This link has already been used.")
    return user


def send_user_invite(db: Session, user: User) -> str:
    """Issue a fresh invite token, email the magic link, mark invited.
    Returns the link (used by dev responses and onboarding flows)."""
    token = create_invite_token(str(user.id))
    try:
        link = email_service.send_invite_email(user.email, user.name, token)
    except Exception as exc:  # noqa: BLE001 — logged, then re-raised unchanged
        # This path does NOT swallow (the caller gets a 500 and invite_sent_at
        # stays unset, which is correct — nothing was sent). It is logged anyway
        # so the invite failure appears in the same greppable form as the reset
        # failure above: the same provider outage takes both features out, and a
        # bare uvicorn traceback does not say which feature the caller lost.
        logger.error(
            "invite email FAILED for %s: %s",
            user.email, email_service.describe_send_failure(exc, redact=(token,)),
        )
        raise
    user.invite_sent_at = datetime.utcnow()
    return link


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.email == payload.email,
        User.is_active == True
    ).first()
    if not user or not verify_password(payload.password, user.password_hash):
        record_login_event(
            db, event_type="password", success=False, request=http_request,
            user_id=user.id if user else None,
            studio_id=user.studio_id if user else None,
            email_attempted=payload.email,
            detail="no active user" if not user else "wrong password",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    access_token = create_access_token(str(user.id), user.role)
    record_login_event(
        db, event_type="password", success=True, request=http_request,
        user_id=user.id, studio_id=user.studio_id, email_attempted=user.email,
    )
    return LoginResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    # Stateless JWT: logout is client-side. Endpoint exists for future revocation.
    return {"message": "logged out"}


# ── Shared-device PIN login (Phase 1b) ────────────────────────────────────
# Public: a shared front-desk tablet. Enter the studio code -> pick a name ->
# enter a PIN. Same generic-error / capped-results enumeration guards as the
# onboarding routes; PIN check is constant-time-ish. Add edge rate-limiting in
# production — there is no in-process limiter here.
@router.post("/shared/lookup", response_model=StudioLookupResponse)
def shared_lookup(payload: StudioLookupRequest, db: Session = Depends(get_db)):
    """Resolve a studio by short name / onboard code and list the instructors
    who have a PIN set (name only)."""
    studio = resolve_studio_by_code(db, payload.studio_code)
    if not studio:
        raise HTTPException(status_code=404, detail=_SHARED_LOGIN_FAILED)

    # An instructor appears at every studio they teach at — their primary
    # studio OR any active user_studios membership.
    from sqlalchemy import or_
    from app.models.user_studio import UserStudio
    member_subq = db.query(UserStudio.user_id).filter(
        UserStudio.studio_id == studio.id, UserStudio.is_active == True)
    instructors = (
        db.query(User.id, User.name)
        .filter(User.role == "instructor",
                User.is_active == True,
                User.pin_hash.isnot(None),
                or_(User.studio_id == studio.id, User.id.in_(member_subq)))
        .order_by(User.name)
        .limit(MAX_SHARED_INSTRUCTORS)
        .all()
    )
    return StudioLookupResponse(
        studio=StudioLite(id=studio.id, name=studio.display_name or studio.name),
        instructors=[InstructorLite(id=i.id, name=i.name) for i in instructors],
    )


@router.post("/shared/login", response_model=LoginResponse)
def shared_login(payload: SharedLoginRequest, http_request: Request, db: Session = Depends(get_db)):
    """Verify name + PIN within a studio, then mint a short-lived studio-scoped
    session. Every failure mode returns the same generic 401."""
    studio = resolve_studio_by_code(db, payload.studio_code)
    user = None
    if studio:
        from sqlalchemy import or_
        from app.models.user_studio import UserStudio
        member_subq = db.query(UserStudio.user_id).filter(
            UserStudio.studio_id == studio.id, UserStudio.is_active == True)
        user = (
            db.query(User)
            .filter(User.id == payload.user_id,
                    User.role == "instructor",
                    User.is_active == True,
                    or_(User.studio_id == studio.id, User.id.in_(member_subq)))
            .first()
        )
    # Always run one bcrypt verify — against the real hash or a dummy — so a
    # miss can't be told from a wrong PIN by timing.
    stored = user.pin_hash if (user and user.pin_hash) else _DUMMY_PIN_HASH
    pin_ok = verify_password(normalize_pin(payload.pin), stored)
    if not studio or not user or not user.pin_hash or not pin_ok:
        record_login_event(
            db, event_type="shared_pin", success=False, request=http_request,
            user_id=user.id if user else None,
            studio_id=studio.id if studio else None,
            detail=("unknown studio code" if not studio
                    else "unknown instructor" if not user
                    else "no PIN set" if not user.pin_hash else "wrong PIN"),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SHARED_LOGIN_FAILED)

    token = _mint_shared_session_token(user, studio.id)
    record_login_event(
        db, event_type="shared_pin", success=True, request=http_request,
        user_id=user.id, studio_id=studio.id, email_attempted=user.email,
    )
    return LoginResponse(access_token=token, user=UserResponse.model_validate(user))


def _may_manage_user(db: Session, actor: User, target: User, operating_studio_id) -> bool:
    """Who may send a user a setup email: an admin, a studio owner/manager of the
    target's studio, a franchise manager whose franchise contains it, or a
    franchise owner inviting a (reporting) user in their own franchise."""
    # An UNRESTRICTED admin (no operating studio selected) reaches everyone.
    # An admin who HAS narrowed to a studio via X-Studio-Id must not bypass
    # that narrowing here -- CLAUDE.md: "X-Studio-Id binds admins too." Falling
    # through to the checks below sends the admin through the same
    # `get_managed_studio_ids(..., operating_studio_id=...)` narrowing a studio
    # owner/manager gets, which correctly resolves to {operating_studio_id} for
    # an admin (see `get_managed_studio_ids`).
    if actor.role == "admin" and not operating_studio_id:
        return True
    # Franchise OWNER inviting someone who belongs to their own franchise (e.g.
    # a reporting user they just added — these often have no studio at all).
    # Reports-only users are not owners, so they can't invite.
    owned_franchise = get_franchise_owner_franchise_id(db, actor)
    if owned_franchise and is_user_in_franchise(db, target, owned_franchise):
        return True
    if not target.studio_id:
        return False
    managed = get_managed_studio_ids(db, actor, operating_studio_id=operating_studio_id)
    if managed and target.studio_id in managed:
        return True
    fid = get_managed_franchise_id(db, actor)
    if fid and fid != "ALL" and target.studio_id in get_franchise_studio_ids_for_reporting(db, fid):
        return True
    return False


# ── Invite / magic-link onboarding (Phase 0) ──────────────────────────────
def _load_invite_target(db: Session, user_id) -> User:
    """The active user an invite-style action is aimed at, or 404.

    Shared by `/invite` and `/setup-link` on purpose. This file's raw
    `db.query(User)` count is frozen at 7 in `tests/test_data_layer_contract.py`
    and may only shrink, so `/setup-link` could not bring its own lookup — and
    `app/data/auth_lookup.py` is not the home for it either: that module is
    documented as PRE-auth only, and both of these run with an authenticated,
    authorised caller. One shared fetch is the honest answer to both.
    """
    target = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found or inactive")
    return target


@router.post("/invite", response_model=InviteResponse)
def invite_user(
    request: InviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    target = _load_invite_target(db, request.user_id)
    if not target.email:
        raise HTTPException(status_code=400, detail="This user has no email address yet.")
    if not _may_manage_user(db, current_user, target, operating_studio_id):
        raise HTTPException(status_code=403,
                            detail="Sending a setup email requires admin, or a studio or franchise owner/manager.")

    link = send_user_invite(db, target)
    db.commit()
    return InviteResponse(
        sent=True,
        email=target.email,
        invite_link=None if email_service.is_live() else link,
    )


@router.post("/setup-link", response_model=SetupLinkResponse)
def issue_setup_link(
    request: InviteRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    """Mint a set-password link and RETURN it, without sending any email.

    Why this exists: outbound email is a single point of failure
    for the only self-service way back into an account. When the provider
    rejected the app's credential, `/auth/forgot-password` and `/auth/invite`
    both went dark and there was no way to get anyone a password without SSH.
    This gives the person who is already allowed to manage that account a link
    they can read out, text, or hand over at the front desk.

    Why returning the link in production is safe: this endpoint reuses the EXACT
    gate of `PUT /api/users/{id}` — literally `users._require_user_admin` +
    `users._require_target_in_scope`, imported rather than re-implemented — so a
    caller who can obtain a link here could already set that user's password
    outright by calling that endpoint. The link grants no capability its holder
    did not have; it is the politer version, because the user chooses their own
    password and the manager never learns it.

    IT DELIBERATELY DOES NOT USE `_may_manage_user`, which `/auth/invite` uses.
    That gate is WIDER — it also admits franchise owners and franchise managers,
    and it applies no target-role check. That is correct for `/invite`, where the
    token is emailed to the TARGET's own inbox and a mistake is a nuisance. It is
    NOT correct here, where the token is handed to the CALLER and a mistake is an
    account takeover: `get_managed_studio_ids` returns an empty set for franchise
    roles by design ("franchise roles get NO studio client data"), so under the
    old gate a franchise owner — who is 403 on `PUT /api/users/{id}` — could mint
    a link for any instructor in the franchise, set the password, and sign in as
    studio staff. Copying the gate without re-deriving the consequence was the
    bug — caught before this ever shipped.

    Binding the two gates together in code, not in prose, is the point: they
    cannot drift, and `test_setup_link.py` asserts the invariant directly.

    (`InviteResponse.invite_link` is suppressed in production for a different
    reason: that field rides a response whose purpose is "an email was sent",
    where an unexpected link would be a leak, not a request.)

    Works for a NEW account and for a forgotten password alike: an invite token
    is rejected once it predates `password_set_at`, so a fresh one issued here
    supersedes anything outstanding and the last link issued is the only live one.
    """
    target = _load_invite_target(db, request.user_id)
    if not target.email:
        # Not a formality: sign-in is by email + password, so a password this
        # user set would be unusable. PIN-only instructors sign in on the shared
        # device instead — give them a PIN, not a link.
        raise HTTPException(
            status_code=400,
            detail="This user has no email address yet, so they cannot sign in with a password. "
                   "Add an email first, or set a shared-device PIN instead.",
        )
    # THE SAME GATE AS `PUT /api/users/{id}`, imported from that module so the
    # two cannot drift. `_require_user_admin` also honours `X-Studio-Id`, so an
    # admin focused into one studio cannot mint a link for another's staff
    # (CLAUDE.md: "X-Studio-Id binds admins too"). `_require_target_in_scope`
    # adds the target-role check `_may_manage_user` lacks, so a studio owner
    # cannot mint a link for an admin or manager sitting in their own studio and
    # escalate through it.
    from app.routes.users import _require_user_admin, _require_target_in_scope

    managed = _require_user_admin(current_user, db, operating_studio_id=operating_studio_id)
    _require_target_in_scope(
        target, managed, current_user.role == "admin", current_user.id,
        "You can only issue a setup link for your own studio's instructors.",
    )

    token = create_invite_token(str(target.id))
    # Same stamp the emailed path sets: an invite WAS issued, and the owners
    # screens read `invited` off this column. Leaving it null would report
    # "not invited" for someone who was handed a working link.
    target.invite_sent_at = datetime.utcnow()
    # The link itself is deliberately NOT recorded — an audit row that carried
    # the token would be a credential at rest in a table the admin log renders.
    record_login_event(
        db, event_type="setup_link_issued", success=True, request=http_request,
        user_id=target.id, actor_user_id=current_user.id, studio_id=target.studio_id,
        email_attempted=target.email,
        detail=f"issued by {current_user.email or current_user.name}"[:255],
    )
    db.commit()
    return SetupLinkResponse(
        link=email_service.invite_link(token),
        name=target.name,
        email=target.email,
        expires_in_hours=INVITE_EXPIRE_HOURS,
    )


@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The signed-in user sets their own new password (verifies the current one)."""
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Your current password is incorrect.")
    current_user.password_hash = hash_password(request.new_password)
    current_user.password_set_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/invite/{token}", response_model=InviteInfoResponse)
def invite_info(token: str, db: Session = Depends(get_db)):
    """Validate a magic link before showing the set-password form."""
    user = _load_invited_user(db, token)
    return InviteInfoResponse(valid=True, name=user.name, email=user.email)


@router.post("/set-password", response_model=LoginResponse)
def set_password(request: SetPasswordRequest, db: Session = Depends(get_db)):
    """Consume an invite token, set the password, and log the user in."""
    user = _load_invited_user(db, request.token)
    user.password_hash = hash_password(request.password)
    user.password_set_at = datetime.utcnow()  # also kills the used token
    db.commit()
    db.refresh(user)
    access_token = create_access_token(str(user.id), user.role)
    return LoginResponse(access_token=access_token, user=UserResponse.model_validate(user))


# ── Self-service password reset ───────────────────────────────────────────
# Public: no auth dependency, same style as /shared/lookup and /shared/login.
# The enumeration-safety shape mirrors shared_login above — every outcome
# (matched or not) does the same visible work and returns the same response,
# so a caller can't tell from timing or payload whether an email is a user.
#
# Unlike /shared/lookup and /shared/login, a match here has a real external
# side effect — one email sent through the shared Resend/SMTP account — and
# this codebase has no rate limiter anywhere (every other public route's
# comments defer that to the edge/WAF, and the prod Caddy image is stock
# caddy:2-alpine with no rate-limit plugin compiled in, so that "edge" layer
# isn't actually configured today). Without a guard, a known email could be
# used to email-bomb its owner and burn the shared provider quota for every
# other feature that sends mail (invites, client reports, session backups).
# This in-memory, per-user cooldown closes that specific gap without adding
# new infrastructure. Keyed by user id (only ever set for a REAL matched
# user), so an attacker enumerating fake emails cannot grow this dict — it's
# bounded by the app's actual active-user count. Per-process/in-memory is
# fine for this single-container deployment (no autoscaling); would need a
# shared store (e.g. the DB) if that ever changes.
RESET_EMAIL_COOLDOWN_SECONDS = int(os.getenv("RESET_EMAIL_COOLDOWN_SECONDS", "60"))
_last_reset_email_sent_at: dict[str, float] = {}


def _reset_email_on_cooldown(user_id) -> bool:
    key = str(user_id)
    now = time.monotonic()
    last = _last_reset_email_sent_at.get(key)
    if last is not None and (now - last) < RESET_EMAIL_COOLDOWN_SECONDS:
        return True
    _last_reset_email_sent_at[key] = now
    return False


def _send_reset_email_and_log(db: Session, user: User, token: str, email_attempted: str) -> None:
    """Runs as a FastAPI BackgroundTask, AFTER the response has already been
    sent to the caller. Critical for enumeration-safety, not just UX: send_email()
    is a real blocking network call (SMTP/Resend) that only ever happens for a
    matched email — doing it inline, before responding, would make the matched
    and unmatched branches of forgot_password() take measurably different
    wall-clock time even though their response bodies are identical, which is
    itself a usable timing oracle for "does this email have an account".
    Scheduling it here means BOTH branches respond after the same fast,
    network-free work (a DB lookup, a JWT sign), and the slow I/O happens off
    the critical path where its timing can't be observed by the caller.
    (`db` stays valid here: FastAPI runs background tasks before a yield
    dependency's post-yield/cleanup code, specifically so this pattern works.)
    """
    try:
        email_service.send_reset_password_email(user.email, user.name, token)
    except Exception as exc:  # noqa: BLE001 — a send failure must not change the response
        # LOG IT. Swallowing the provider error silently here would mean a
        # total outbound-email outage (e.g. a 535 from the SMTP host)
        # produces nothing but an opaque login_events row and goes unnoticed.
        # The message names the feature and carries the scrubbed provider
        # error so `grep "password reset email"` on the container log is
        # enough to diagnose it.
        failure = email_service.describe_send_failure(exc, redact=(token,))
        logger.error("password reset email FAILED for %s: %s", user.email, failure)
        record_login_event(
            db, event_type="password_reset_requested", success=False,
            user_id=user.id, studio_id=user.studio_id, email_attempted=email_attempted,
            # The exception TYPE only — never the provider's message. This row is
            # rendered on the admin Login Log screen, so it makes the failure
            # diagnosable without SSH; a message could smuggle provider text
            # (worst case a credential) into the database.
            detail=f"email send failed: {type(exc).__name__}",
        )
        return
    record_login_event(
        db, event_type="password_reset_requested", success=True,
        user_id=user.id, studio_id=user.studio_id, email_attempted=email_attempted,
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
):
    user = get_active_user_by_email(db, payload.email)
    if not user:
        record_login_event(
            db, event_type="password_reset_requested", success=False,
            email_attempted=payload.email, detail="no active user",
        )
    elif _reset_email_on_cooldown(user.id):
        record_login_event(
            db, event_type="password_reset_requested", success=False,
            user_id=user.id, studio_id=user.studio_id, email_attempted=payload.email,
            detail="cooldown",
        )
    else:
        token = create_reset_token(str(user.id))
        background_tasks.add_task(_send_reset_email_and_log, db, user, token, payload.email)
    return ForgotPasswordResponse(sent=True)


@router.get("/reset-password/{token}", response_model=ResetPasswordInfoResponse)
def reset_password_info(token: str, db: Session = Depends(get_db)):
    """Validate a reset link before showing the choose-new-password form."""
    user = _load_reset_user(db, token)
    return ResetPasswordInfoResponse(valid=True, name=user.name, email=user.email)


@router.post("/reset-password", response_model=LoginResponse)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Consume a reset token, set the new password, and log the user in."""
    user = _load_reset_user(db, request.token)
    user.password_hash = hash_password(request.password)
    user.password_set_at = datetime.utcnow()  # also kills this and any other outstanding token
    db.commit()
    db.refresh(user)
    access_token = create_access_token(str(user.id), user.role)
    record_login_event(
        db, event_type="password_reset_completed", success=True,
        user_id=user.id, studio_id=user.studio_id, email_attempted=user.email,
    )
    return LoginResponse(access_token=access_token, user=UserResponse.model_validate(user))


# Admin impersonation (testing aid): issues a normal access token for the
# TARGET user. The frontend keeps the admin's own token stored locally and
# swaps back on "return to admin" — no server state involved.
@router.post("/impersonate/{user_id}", response_model=LoginResponse)
def impersonate(
    user_id: UUID,
    http_request: Request,
    studio_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    operating_studio_id: Optional[UUID] = Depends(get_operating_studio_id),
):
    target = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    # Scope the impersonation to a studio so the impersonated (non-admin)
    # instructor only sees that studio's data (dashboard, clients, resume,
    # history). Explicit ?studio_id wins (the browse page knows which studio);
    # otherwise fall back to the admin's currently-selected operating studio.
    osid = studio_id or operating_studio_id
    if osid and not db.query(Studio.id).filter(Studio.id == osid).first():
        osid = None

    access_token = create_access_token(
        str(target.id), target.role,
        operating_studio_id=str(osid) if osid else None,
        impersonated_by=str(admin.id),
    )
    record_login_event(
        db, event_type="impersonation", success=True, request=http_request,
        user_id=target.id, actor_user_id=admin.id, studio_id=osid,
        email_attempted=target.email,
        detail=f"admin {admin.email} impersonated {target.email}",
    )
    return LoginResponse(
        access_token=access_token,
        user=UserResponse.model_validate(target),
    )
