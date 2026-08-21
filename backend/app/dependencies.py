from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt

from app.database import SessionLocal
from app.models.user import User
from app.utils.tokens import decode_token

bearer_scheme = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Only real login / impersonation / shared-device tokens (type="access")
    # authenticate here. Invite, report and studio-sync tokens have their own
    # dedicated decoders and must NEVER be usable as an access token — an emailed
    # magic link is not a login.
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def get_operating_studio_id(
    x_studio_id: Optional[str] = Header(None, alias="X-Studio-Id"),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Optional[UUID]:
    """The studio the caller is operating within. Two trusted sources:

    1. An `osid` claim baked into the token by an admin at impersonation time.
       This takes precedence and is what keeps an impersonated (non-admin)
       instructor scoped to the studio the admin picked — the X-Studio-Id header
       is admin-only and ignored for non-admins, so without this the instructor
       would fall back to their own (possibly unrestricted) visibility.
    2. The X-Studio-Id header an ADMIN sends after selecting a studio.

    Returns None when unset/malformed/nonexistent — the caller's normal
    visibility then applies (for an admin, that's all studios)."""
    from app.models.studio import Studio

    def _valid(raw):
        try:
            sid = UUID(str(raw))
        except (ValueError, TypeError):
            return None
        return sid if db.query(Studio.id).filter(Studio.id == sid).first() else None

    # (1) Token-baked operating studio (admin-minted at impersonation) wins.
    try:
        osid = decode_token(credentials.credentials).get("osid")
    except Exception:
        osid = None
    if osid:
        sid = _valid(osid)
        if sid:
            return sid

    # (2) A studio selected via the X-Studio-Id header. Admins may focus ANY
    # studio; other staff only a studio within their OWN scope (ownership ∪
    # instructor memberships ∪ primary). The header only NARROWS visibility, and
    # an out-of-scope / invalid header is ignored (falls back to normal scope) —
    # never a way to reach another studio's data.
    if not x_studio_id:
        return None
    sid = _valid(x_studio_id)
    if not sid:
        return None
    if current_user.role == "admin":
        return sid
    from app.utils.ownership import get_user_ownership_scope, get_instructor_studio_ids
    scope = get_user_ownership_scope(db, current_user)
    allowed = set(scope.studio_ids) | get_instructor_studio_ids(db, current_user)
    if current_user.studio_id:
        allowed.add(current_user.studio_id)
    return sid if sid in allowed else None


def get_impersonator_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Optional[str]:
    """The admin driving this session via impersonation (the token's `act`
    claim), or None for a real login. Endpoints that record per-user state
    (e.g. note dismissals) check this so an impersonated session never
    writes that state as if the real user had acted."""
    try:
        return decode_token(credentials.credentials).get("act")
    except Exception:
        return None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# Role hierarchy: admin > manager > instructor.
# Each role includes ALL abilities of the roles below it — a manager IS an
# instructor. Never check `role == "instructor"` for capabilities; use
# require_staff (or require_instructor, its alias) so managers and admins
# qualify automatically.
#
# Owners are not a role: studio/franchise ownership are relationship rows on
# top of any base role. A future client-facing role is NOT staff.
STAFF_ROLES = {"admin", "manager", "instructor"}


def require_staff(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required",
        )
    return current_user


# Alias: "can this user act as an instructor?" — yes for every staff role,
# per the hierarchy above.
require_instructor = require_staff


def require_setup_access(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Studio setup (equipment, exercises): admin, studio owner, or studio
    manager. Instructors explicitly may NOT create equipment/exercises."""
    if current_user.role in ("admin", "manager"):
        return current_user
    from app.models.studio_owner import StudioOwner
    has_studio_role = (
        db.query(StudioOwner)
        .filter(StudioOwner.user_id == current_user.id, StudioOwner.is_active == True)
        .first()
    )
    if has_studio_role:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Studio owner or manager access required",
    )


def get_managed_franchise_id(db: Session, user: User):
    """The franchise this user MANAGES (level='manager'), or None. Admins
    return 'ALL'. 'reports' level grants no management."""
    if user.role == "admin":
        return "ALL"
    from app.models.franchise_owner import FranchiseOwner
    row = (
        db.query(FranchiseOwner)
        .filter(FranchiseOwner.user_id == user.id, FranchiseOwner.is_active == True,
                FranchiseOwner.level == "manager")
        .first()
    )
    return row.franchise_id if row else None


def require_franchise_management(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Studio lifecycle (create/change/deactivate, contacts) and studio-owner
    assignment: admins and franchise managers only."""
    if get_managed_franchise_id(db, current_user) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Franchise manager access required",
        )
    return current_user
