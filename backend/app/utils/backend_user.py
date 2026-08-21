"""The canonical "Platform Team" platform user.

A single account that owns platform-level communications (team announcements
and admin question replies) so they are attributed to a stable, non-personal
identity instead of whichever human admin happened to be logged in.

It is an ordinary ADMIN — no special role; admin accomplishes the same thing.
The "team" wording is just the UI's label for admin-authored content. Created
with an unusable password; a real one is set through the normal setup-email
flow if someone needs to log in as it.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.password import hash_password

BACKEND_USER_EMAIL = "backend@example.com"
BACKEND_USER_NAME = "Platform Team"


def get_backend_user(db: Session) -> User:
    """Return the Platform Team admin, creating it once if absent.

    Idempotent: keyed on the fixed email, so every environment converges on a
    single row. Safe to call inside a request; the caller commits.
    """
    user = db.query(User).filter(User.email == BACKEND_USER_EMAIL).first()
    if user is None:
        user = User(
            name=BACKEND_USER_NAME,
            email=BACKEND_USER_EMAIL,
            password_hash=hash_password(uuid.uuid4().hex),  # unusable until set via setup flow
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user
