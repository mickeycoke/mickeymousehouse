"""LoginEvent reads for pre-authentication security checks.

Not a scoped repo like the others here: the reads this file exists for
(counting recent failed attempts by IP or by target user, for the onboarding
lockouts in app/routes/onboard.py) happen BEFORE any caller is authenticated —
there is no AccessScope to construct them from. `LoginEvent` is registered
"studio" in MODEL_SCOPE for its existing admin-login-log usage, but these
calls are deliberately cross-studio: an IP is an IP, and a guessing campaign
against one instructor counts the same whichever studio it targets.
"""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models.login_event import LoginEvent


def count_recent_failures(db: DBSession, *, event_type: str, ip_address: str, since: datetime) -> int:
    return (
        db.query(LoginEvent)
        .filter(LoginEvent.event_type == event_type,
                LoginEvent.success == False,  # noqa: E712
                LoginEvent.ip_address == ip_address,
                LoginEvent.created_at >= since)
        .count()
    )


def count_recent_failures_for_user(db: DBSession, *, event_type: str, user_id, since: datetime) -> int:
    """Failed attempts against ONE target account, from ANY IP — the per-IP
    count above can't see a distributed guessing campaign focused on a single
    user (a bulk-imported PIN may be a weak default), so the onboarding
    lockout also counts by target."""
    return (
        db.query(LoginEvent)
        .filter(LoginEvent.event_type == event_type,
                LoginEvent.success == False,  # noqa: E712
                LoginEvent.user_id == user_id,
                LoginEvent.created_at >= since)
        .count()
    )


def count_recent_failures_for_email(db: DBSession, *, event_type: str, email: str,
                                    since: datetime) -> int:
    """Failed attempts against one EMAIL, from any IP.

    Needed as well as the per-user count because the interesting case is an
    address that does not resolve to a user at all: guessing at
    `admin@<studio>.com` must be throttled even when no such account exists, or
    the endpoint becomes a way to find out which addresses are real.
    """
    return (
        db.query(LoginEvent)
        .filter(LoginEvent.event_type == event_type,
                LoginEvent.success == False,  # noqa: E712
                func.lower(LoginEvent.email_attempted) == email.lower(),
                LoginEvent.created_at >= since)
        .count()
    )


def oldest_recent_failure(db: DBSession, *, event_type: str, since: datetime,
                          ip_address=None, email=None, user_id=None):
    """When the failure now holding a lockout happened.

    The lockout clears as that attempt ages out of the window, so this is what
    makes an honest `Retry-After` possible instead of a flat "try again in an
    hour" that is wrong for anyone who already waited.
    """
    q = (
        db.query(LoginEvent.created_at)
        .filter(LoginEvent.event_type == event_type,
                LoginEvent.success == False,  # noqa: E712
                LoginEvent.created_at >= since)
    )
    if user_id is not None:
        q = q.filter(LoginEvent.user_id == user_id)
    elif email:
        q = q.filter(func.lower(LoginEvent.email_attempted) == email.lower())
    elif ip_address:
        q = q.filter(LoginEvent.ip_address == ip_address)
    row = q.order_by(LoginEvent.created_at.asc()).first()
    return row[0] if row else None
