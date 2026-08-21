"""Public, UNAUTHENTICATED instructor self-serve onboarding (Phase 1a).

Flow: an instructor enters their studio's code -> picks their own name from the
studio's UNCLAIMED instructors -> submits their email -> gets a Phase 0 magic
link to set a password.

Security posture (these endpoints face the open internet):
  * No secrets are returned — instructor rows expose id + name only, never
    emails/PINs/roles.
  * Unknown codes get a GENERIC 404 (never "no such studio" vs "no instructors")
    so this can't be walked as a studio/instructor enumeration oracle.
  * Results are capped.
  * Claiming is gated on password_set_at IS NULL: an already-activated account
    can NEVER be re-claimed, which is the guard against identity takeover.

  * In-process rate limiting (B-1): failed studio lookups are limited per IP
    (10/hour), and PIN attempts are limited BOTH per IP and per target user
    (3 failures/hour each) — the per-user axis is what stops a distributed
    guessing campaign against one account from many IPs. All counters live in
    login_events, so they survive a restart. Edge-level rate limiting (reverse
    proxy / WAF) is still worthwhile as defence in depth, but is no longer the
    only line.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.data.login_events import count_recent_failures, count_recent_failures_for_user
from app.dependencies import get_db
from app.models.user import User
from app.routes.auth import _DUMMY_PIN_HASH, send_user_invite
from app.schemas.onboard import (
    ClaimRequest, ClaimResponse, InstructorLite, StudioLite,
    StudioLookupRequest, StudioLookupResponse, VerifyPinRequest, VerifyPinResponse,
)
from app.services import email as email_service
from app.services.login_audit import _client_ip, record_login_event
from app.utils.password import hash_password, normalize_pin, verify_password
from app.utils.studio_lookup import resolve_studio_by_code

router = APIRouter(prefix="/api/onboard", tags=["onboard"])

# Guard against a hostile client pulling a whole studio roster in one call.
MAX_INSTRUCTORS = 500

_GENERIC_NOT_FOUND = "We couldn't find a studio for that code. Check it and try again."
_CANNOT_CLAIM = "This name isn't available to set up. Ask your studio for help."

# The PIN is what stops anyone who knows a studio's public onboard code from
# picking any unclaimed instructor's name and claiming their account with a
# different email. 3 wrong attempts locks the IP out for an hour
# — enforced by counting recent failures in login_events, so it needs no new
# table and survives a restart. The same 3-failures-per-hour cap also applies
# per TARGET USER across all IPs (B-1): without it, a distributed attacker
# could guess one instructor's weak default PIN from many addresses.
MAX_PIN_ATTEMPTS = 3
PIN_LOCKOUT_WINDOW = timedelta(hours=1)

# Failed studio lookups are throttled per IP too (B-1): studio codes are
# guessable, and each hit hands over a studio's unclaimed-instructor
# roster. Successful lookups are never counted — real instructors typo a code
# once or twice, not ten times.
MAX_LOOKUP_FAILURES = 10
LOOKUP_LOCKOUT_WINDOW = timedelta(hours=1)

_TOO_MANY_ATTEMPTS = "Too many attempts. Please try again in an hour."

# Onboarding email branching — a placeholder domain a bulk import can stamp
# on an instructor row that never had a real email captured.
_PLACEHOLDER_EMAIL_SUFFIX = "@import.placeholder.local"

_ALREADY_HAS_EMAIL = "This account already has an email address. Use Forgot password to sign in."


def _is_placeholder_email(email: str | None) -> bool:
    """True when the account has no real email: NULL/empty, or an importer
    placeholder. Case-insensitive; the leading '@' is load-bearing so a
    lookalike domain (e.g. "x@evil-import.placeholder.local") does NOT match."""
    if not email:
        return True
    return email.strip().lower().endswith(_PLACEHOLDER_EMAIL_SUFFIX)


def _pin_locked_out(db: Session, user: User | None, http_request: Request | None) -> bool:
    cutoff = datetime.utcnow() - PIN_LOCKOUT_WINDOW
    ip = _client_ip(http_request)
    # Per-IP axis. If the IP can't be read, fail open, not closed for everyone.
    if ip and count_recent_failures(
            db, event_type="onboard_pin", ip_address=ip, since=cutoff) >= MAX_PIN_ATTEMPTS:
        return True
    # Per-target-user axis — any IP counts, so distributing the attempts
    # across addresses doesn't reset the clock.
    if user is not None and count_recent_failures_for_user(
            db, event_type="onboard_pin", user_id=user.id, since=cutoff) >= MAX_PIN_ATTEMPTS:
        return True
    return False


def _lookup_locked_out(db: Session, http_request: Request | None) -> bool:
    ip = _client_ip(http_request)
    if not ip:
        return False  # same fail-open posture as the PIN lockout
    cutoff = datetime.utcnow() - LOOKUP_LOCKOUT_WINDOW
    recent_failures = count_recent_failures(
        db, event_type="onboard_lookup", ip_address=ip, since=cutoff)
    return recent_failures >= MAX_LOOKUP_FAILURES


def _verify_instructor_pin(db: Session, user: User | None, pin: str, http_request: Request | None) -> None:
    """Raises 429 if this IP or this target user is locked out, 401 if the PIN
    is wrong. Records every attempt (success or failure) so the lockout count
    is durable."""
    if _pin_locked_out(db, user, http_request):
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect PIN attempts. Try again in an hour.",
        )
    stored = user.pin_hash if (user and user.pin_hash) else _DUMMY_PIN_HASH
    pin_ok = verify_password(normalize_pin(pin), stored)
    if not user or not user.pin_hash or not pin_ok:
        record_login_event(
            db, event_type="onboard_pin", success=False, request=http_request,
            user_id=user.id if user else None,
            studio_id=user.studio_id if user else None,
            detail=("unknown instructor" if not user
                    else "no PIN set" if not user.pin_hash else "wrong PIN"),
        )
        raise HTTPException(status_code=401, detail="Incorrect PIN.")
    record_login_event(
        db, event_type="onboard_pin", success=True, request=http_request,
        user_id=user.id, studio_id=user.studio_id, detail=None,
    )


@router.post("/studio-lookup", response_model=StudioLookupResponse)
def studio_lookup(payload: StudioLookupRequest, http_request: Request, db: Session = Depends(get_db)):
    """Resolve a studio by its short name or onboard code and list its
    UNCLAIMED instructors (name never set a password yet)."""
    if _lookup_locked_out(db, http_request):
        raise HTTPException(status_code=429, detail=_TOO_MANY_ATTEMPTS)
    studio = resolve_studio_by_code(db, payload.studio_code)
    if not studio:
        # Only misses count toward the lockout — see MAX_LOOKUP_FAILURES.
        record_login_event(
            db, event_type="onboard_lookup", success=False, request=http_request,
            detail="unknown studio code",
        )
        raise HTTPException(status_code=404, detail=_GENERIC_NOT_FOUND)

    # An instructor is claimable at any studio they teach at — primary OR
    # an active membership.
    from sqlalchemy import or_
    from app.models.user_studio import UserStudio
    member_subq = db.query(UserStudio.user_id).filter(
        UserStudio.studio_id == studio.id, UserStudio.is_active == True)
    instructors = (
        db.query(User.id, User.name)
        .filter(User.role == "instructor",
                User.is_active == True,
                User.password_set_at.is_(None),
                or_(User.studio_id == studio.id, User.id.in_(member_subq)))
        .order_by(User.name)
        .limit(MAX_INSTRUCTORS)
        .all()
    )
    return StudioLookupResponse(
        studio=StudioLite(id=studio.id, name=studio.display_name or studio.name),
        instructors=[InstructorLite(id=i.id, name=i.name) for i in instructors],
    )


def _lookup_claimable_instructor(db: Session, user_id) -> User | None:
    """None if there's no such user, they're not an active instructor, they're
    already claimed, or they have no studio relationship. Shared by verify-pin
    and claim so both apply the exact same claimability rule."""
    user = (
        db.query(User)
        .filter(User.id == user_id,
                User.role == "instructor",
                User.is_active == True)
        .first()
    )
    from app.utils.ownership import get_instructor_studio_ids
    if not user or user.password_set_at is not None or (
        user.studio_id is None and not get_instructor_studio_ids(db, user)
    ):
        return None
    return user


@router.post("/verify-pin", response_model=VerifyPinResponse)
def verify_pin(payload: VerifyPinRequest, http_request: Request, db: Session = Depends(get_db)):
    """Confirm the PIN before the onboarding flow moves on to asking for an
    email — early, specific feedback, not just a generic claim failure. The
    real enforcement is in claim() below (this can't be bypassed by skipping
    straight to that endpoint), but checking here first is what lets the UI
    show "wrong PIN" at the moment it's wrong."""
    user = _lookup_claimable_instructor(db, payload.user_id)
    _verify_instructor_pin(db, user, payload.pin, http_request)
    db.commit()  # persist the login_events row from _verify_instructor_pin
    # `user` is guaranteed non-None here: _verify_instructor_pin raises 401
    # for a None user before this line. needs_setup is a single bit revealed
    # only after PIN proof, under the existing lockouts -- this isn't a PII
    # leak the way returning the address itself would be.
    return VerifyPinResponse(ok=True, needs_setup=_is_placeholder_email(user.email))


@router.post("/claim", response_model=ClaimResponse)
def claim(payload: ClaimRequest, http_request: Request, db: Session = Depends(get_db)):
    """An instructor claims their own record. Only an UNCLAIMED instructor can
    be claimed, and only with their real PIN — without this, anyone who knows
    the studio's public onboard code could claim any unclaimed name with an
    email of their own choosing.

    Two modes, both requiring the same PIN proof:
      * payload.password ABSENT — legacy magic-link invite (kept for API
        compatibility; the current UI no longer uses it for placeholder-email
        instructors, but nothing else depends on removing it).
      * payload.password PRESENT — combined setup: sets email AND password in
        one step, no email round-trip. Only reachable for an instructor whose
        CURRENT email is a placeholder — a real-email instructor is rejected
        in BOTH modes (see the 409 below), matching the owner's rule that no
        new-account setup happens once a real email already exists; those
        instructors use Forgot Password instead.
    """
    email = payload.email.strip().lower()

    # Not a claimable instructor, or already activated -> one generic error, so
    # a prober can't tell "no such user" from "already set up" (identity guard).
    user = _lookup_claimable_instructor(db, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_CANNOT_CLAIM)

    _verify_instructor_pin(db, user, payload.pin, http_request)

    # B10: a real email already on file means there is nothing to set up here
    # — regardless of mode. The UI no longer routes these instructors to this
    # form at all (they see the Forgot Password message instead), so a
    # request that reaches this branch is a direct API caller.
    if not _is_placeholder_email(user.email):
        raise HTTPException(status_code=409, detail=_ALREADY_HAS_EMAIL)

    # The email must not already belong to someone else (would collide on the
    # unique users.email and could hijack another account's invite).
    taken = (
        db.query(User.id)
        .filter(User.email == email, User.id != user.id)
        .first()
    )
    if taken:
        raise HTTPException(status_code=400, detail="That email address is already in use.")

    user.email = email

    if payload.password:
        # Combined setup: activate immediately, no link to click. Do NOT call
        # send_user_invite — its token would be rejected as issued before
        # password_set_at (_load_invited_user in app/routes/auth.py), and
        # invite_sent_at would record a magic-link invite that never went out.
        user.password_hash = hash_password(payload.password)
        user.password_set_at = datetime.utcnow()
        db.commit()
        return ClaimResponse(sent=False, email=email, invite_link=None, activated=True)

    link = send_user_invite(db, user)  # issues token, emails link, marks invite_sent_at
    db.commit()
    return ClaimResponse(
        sent=True,
        email=email,
        invite_link=None if email_service.is_live() else link,
        activated=False,
    )
