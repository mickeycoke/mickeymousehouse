"""Pre-authentication user lookups — a narrow, deliberate exception.

Every other read of `User` goes through `app/dependencies.py`'s scope
machinery, which assumes a request already knows WHO it is (an
`AccessScope` built from an authenticated session / `X-Studio-Id`). The two
functions here exist for the moment *before* that: establishing WHO is
authenticating in the first place, on public routes like `/login`,
`/forgot-password`, and `/reset-password`. There is no studio context to
scope by yet — the studio is a property of the row we are trying to find.

This is structurally identical to the raw `db.query(User)` already inside
`login()` in `app/routes/auth.py` (grandfathered into that file's
`LEGACY_BUDGET`) — a single-row fetch by a unique key (email, or a token's
`sub`), never a list, and never reused after authentication succeeds. It
lives here instead of growing that budget because `app/data/` is the
mechanism by which new code is required to go through a reviewable, narrow
surface rather than another ad hoc raw query scattered through a route file.

Do not add anything else here. A list, a search, or any lookup used after
the caller is authenticated belongs in a real scoped repo, not this file.
"""
from sqlalchemy.orm import Session

from app.models.user import User


def get_active_user_by_email(db: Session, email: str) -> User | None:
    """The active user with this email, or None. Used only to decide who is
    attempting to log in / reset a password — never post-auth."""
    return db.query(User).filter(User.email == email, User.is_active == True).first()


def get_active_user_by_id(db: Session, user_id) -> User | None:
    """The active user with this id, or None. Used only to resolve a
    pre-auth token's `sub` claim back to a user — never post-auth."""
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()
