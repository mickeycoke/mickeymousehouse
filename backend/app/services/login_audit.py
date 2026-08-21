"""Record authentication events for the admin login log.

Deliberately best-effort: an audit write must NEVER break a sign-in. Every
helper swallows its own errors.

The row is written in its OWN session on the request session's engine, never
through the request session itself. Two reasons:
  * durability — a failed login raises 401, so the request transaction is never
    committed; an independent transaction still records the attempt.
  * isolation — the test suite hands endpoints a session whose fixture data is
    flushed, not committed, and rolled back at teardown. Committing that shared
    session would persist the fixture rows and leak them into later tests.
"""
import logging

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.models.login_event import LoginEvent

logger = logging.getLogger(__name__)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # Behind Caddy, uvicorn runs with --proxy-headers so request.client.host is
    # already the real client; fall back to the first X-Forwarded-For hop.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else None)


def record_login_event(db: Session, *, event_type: str, success: bool,
                       request: Request | None = None, user_id=None,
                       actor_user_id=None, studio_id=None,
                       email_attempted: str | None = None,
                       detail: str | None = None) -> None:
    """Persist one login-audit row in its own transaction. Never raises."""
    audit_session = None
    try:
        ua = request.headers.get("user-agent") if request else None
        event = LoginEvent(
            event_type=event_type,
            success=success,
            user_id=user_id,
            actor_user_id=actor_user_id,
            studio_id=studio_id,
            email_attempted=(email_attempted or None) and email_attempted[:255],
            ip_address=_client_ip(request),
            user_agent=ua,
            detail=(detail or None) and detail[:255],
        )
        # Same database, separate connection + transaction — see module docstring.
        audit_session = sessionmaker(bind=db.get_bind())()
        audit_session.add(event)
        audit_session.commit()
    except Exception as exc:   # audit must never break authentication
        # NO `exc_info`/`logger.exception` here, deliberately.
        # This helper is called from inside `except` blocks — notably
        # auth.py's reset-email failure handler — so Python would render the
        # CHAINED "During handling of the above exception" traceback, which
        # carries the outer exception's UNSCRUBBED text. That text is
        # provider-controlled and can contain the reset token (some clients
        # stringify the request body they sent), which is a live credential.
        # auth.py scrubs its own line via email.describe_send_failure(); a
        # traceback here would print the raw one straight past that guard.
        # The audit write's own failure is a DB error with a shallow,
        # predictable stack — type plus message is the whole diagnostic.
        logger.error(
            "login audit write failed (%s, success=%s): %s: %s",
            event_type, success, type(exc).__name__, " ".join(str(exc).split()),
        )
        if audit_session is not None:
            try:
                audit_session.rollback()
            except Exception:
                pass
    finally:
        if audit_session is not None:
            try:
                audit_session.close()
            except Exception:
                pass
