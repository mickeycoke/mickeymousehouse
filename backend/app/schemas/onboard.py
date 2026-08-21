"""Schemas for the public onboarding + shared-device login flows (Phase 1).

These back UNAUTHENTICATED endpoints, so every response is deliberately thin:
studios and instructors expose id + name ONLY — never emails, PINs, or roles.
"""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class StudioLite(BaseModel):
    id: UUID
    name: str


class InstructorLite(BaseModel):
    id: UUID
    name: str


# ── studio lookup (shared by /onboard and /auth/shared) ────────────────────
class StudioLookupRequest(BaseModel):
    studio_code: str


class StudioLookupResponse(BaseModel):
    studio: StudioLite
    instructors: List[InstructorLite]


# ── self-serve claim ───────────────────────────────────────────────────────
# The PIN proves you actually ARE the instructor you picked from the public
# name list — without it, anyone who knows a studio's onboard code could pick
# any unclaimed name and set their own email on that account.
class VerifyPinRequest(BaseModel):
    user_id: UUID
    pin: str


class VerifyPinResponse(BaseModel):
    ok: bool
    # True when the instructor has no real email on file (NULL/empty, or an
    # importer placeholder ending in @import.placeholder.local) -- the client
    # shows the combined email+password setup form (onboarding email
    # branching). False -> a real email already exists, so the client points
    # them at Forgot Password instead of any setup form. Deliberately a
    # single bit, never the address itself -- see the docstring above.
    needs_setup: bool = False


class ClaimRequest(BaseModel):
    user_id: UUID
    pin: str
    email: EmailStr
    # Present -> combined setup (B10): set email AND password in one step, no
    # magic-link round-trip. Absent -> legacy magic-link invite behavior,
    # kept for API compatibility.
    password: Optional[str] = Field(default=None, min_length=8)


class ClaimResponse(BaseModel):
    sent: bool
    email: Optional[str] = None
    # Populated ONLY under the console email backend (dev), so the magic-link
    # flow is testable without a provider. Never returned in production.
    invite_link: Optional[str] = None
    # True when the combined path ran (B10): password is set, the account is
    # active, and the instructor can sign in right now -- no link to click.
    activated: bool = False


# ── shared-device PIN login ────────────────────────────────────────────────
class SharedLoginRequest(BaseModel):
    studio_code: str
    user_id: UUID
    pin: str
