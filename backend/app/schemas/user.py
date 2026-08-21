from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class UserCreate(BaseModel):
    timezone: Optional[str] = None
    # Optional: PIN-only instructors have no email. Required for anyone who logs
    # in by email/password or needs a setup-email invite.
    email: Optional[EmailStr] = None
    name: str
    # Optional: leave blank to create the account unusable-until-invited, then
    # send them a setup email so they choose their own password (Phase 0).
    password: Optional[str] = None
    role: str = "instructor"
    studio_id: Optional[UUID] = None


class UserUpdate(BaseModel):
    timezone: Optional[str] = None
    name: Optional[str] = None
    studio_id: Optional[UUID] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    timezone: Optional[str] = None
    id: UUID
    email: Optional[str] = None
    name: str
    role: str
    is_active: bool
    studio_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user: UserResponse


# ── Invite / magic-link onboarding (Phase 0) ──────────────────────────────
class InviteRequest(BaseModel):
    user_id: UUID


class InviteResponse(BaseModel):
    sent: bool
    email: Optional[str] = None
    # Populated ONLY when the console email backend is active (dev), so the
    # flow is testable without a provider. Never returned in production.
    invite_link: Optional[str] = None


class InviteInfoResponse(BaseModel):
    valid: bool
    name: Optional[str] = None
    email: Optional[str] = None


class SetupLinkResponse(BaseModel):
    """A set-password link handed to an authorised manager to pass on by hand,
    instead of being emailed. Unlike InviteResponse.invite_link this is returned
    in PRODUCTION too — see the endpoint for why that grants no new power."""
    link: str
    name: str
    email: str
    expires_in_hours: int


class SetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


# ── Self-service password reset ────────────────────────────────────────────
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    # Deliberately NO conditional dev-link field (unlike InviteResponse).
    # This is a PUBLIC, unauthenticated endpoint — the response must be
    # byte-for-byte identical whether or not the email matched a user, so it
    # must never carry a field whose presence/absence reveals that. (Devs can
    # still get the link from the console-backend log line same as any other
    # console email.)
    sent: bool


class ResetPasswordInfoResponse(BaseModel):
    valid: bool
    name: Optional[str] = None
    email: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


# ── Shared-device PIN management (studio owner/manager) ────────────────────
class PinResponse(BaseModel):
    """Current shared-device PIN for one instructor. `pin` is null when no PIN
    is set, or when a legacy/imported PIN exists only as a hash (has_pin true,
    pin null) — reset it to make it viewable again."""
    user_id: UUID
    name: str
    pin: Optional[str] = None
    has_pin: bool


class PinUpdate(BaseModel):
    # Send null / "" to clear the PIN. NEW pins are 4–8 digits.
    # Note: a bulk-imported PIN may be alphanumeric — those are entered via
    # the shared-login "type it" field, but new ones set here are numeric.
    pin: Optional[str] = None

    @field_validator("pin")
    @classmethod
    def _valid_pin(cls, v):
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        if not (v.isdigit() and 4 <= len(v) <= 8):
            raise ValueError("PIN must be 4 to 8 digits")
        return v
