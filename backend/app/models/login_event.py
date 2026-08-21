from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.database import Base


class LoginEvent(Base):
    """An append-only audit row for every authentication attempt.

    One table covers all sign-in paths so the admin log is a single stream:
      - password        (POST /api/auth/login)
      - shared_pin      (POST /api/auth/shared/login — front-desk tablet)
      - onboard_pin     (POST /api/onboard/verify-pin, /api/onboard/claim —
                          self-serve instructor onboarding; also the source
                          for the 3-strikes-per-hour-per-IP onboarding lockout)
      - impersonation   (POST /api/auth/impersonate/{id} — admin acting as user)

    `success=False` rows capture failed attempts (wrong password/PIN); on those
    `user_id` may be null (no user matched) and `email_attempted` holds what was
    typed. `actor_user_id` is the admin on an impersonation row; `user_id` is the
    account that was signed into (the target). Times are UTC.
    """
    __tablename__ = "login_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    event_type = Column(String(32), nullable=False)   # password | shared_pin | impersonation
    success = Column(Boolean, nullable=False, default=False)
    # The account signed into (null on a failed login with no matching user).
    # ON DELETE SET NULL on every FK below: an audit trail must never block
    # deleting a user or studio, and the event itself (time, IP, outcome) stays
    # meaningful without the link.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    # The initiator, when different from the subject (the admin on impersonation).
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True)
    # Studio context, when the path knows it (shared-device login, impersonation).
    studio_id = Column(UUID(as_uuid=True), ForeignKey("studios.id", ondelete="SET NULL"),
                       nullable=True, index=True)
    # The email involved: what was typed on a failed login, and the account's
    # own email on a success — recorded here so the log still says WHO even
    # after the user row is deleted and user_id goes null.
    email_attempted = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    # Short human note: failure reason, or extra context.
    detail = Column(String(255), nullable=True)
