import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable: PIN-only instructors (shared-device login) have no email and no
    # password login. Still UNIQUE — Postgres treats NULLs as distinct, so any
    # number of null-email instructors coexist. Email/password login and invites
    # simply require an email to be present.
    email = Column(String(255), unique=True, nullable=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="instructor")
    studio_id = Column(UUID(as_uuid=True), nullable=True)
    timezone = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # Onboarding/invite lifecycle (Phase 0). invite_sent_at: an invite email
    # was sent. password_set_at: the user completed set-password — also the
    # single-use guard for invite tokens (a token issued before this is dead).
    invite_sent_at = Column(DateTime, nullable=True)
    password_set_at = Column(DateTime, nullable=True)
    # Phase 1b: personal PIN for shared-device login. pin_hash backs the
    # constant-time login verify; pin is the recoverable plaintext so studio
    # owners/managers can view and hand out the code (it's a low-security
    # convenience PIN — the tablet is already signed into the studio account).
    pin_hash = Column(String(255), nullable=True)
    pin = Column(String(16), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
