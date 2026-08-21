"""Resolve a studio from the code a user types during onboarding / shared login.

A studio is identified by `studios.short_name` (checked first) or
`studios.onboard_code` (fallback, for studios with no short name), both
matched case-insensitively.

Returns the (active) Studio or None. Callers MUST translate a None into a
generic "not found" so this never becomes a studio/instructor enumeration oracle.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.studio import Studio


def resolve_studio_by_code(db: Session, code: str) -> Studio | None:
    code = (code or "").strip()
    if not code:
        return None

    # 1) short_name — the code studios already know (case-insensitive).
    studio = (
        db.query(Studio)
        .filter(func.upper(Studio.short_name) == code.upper(),
                Studio.is_active == True)
        .first()
    )
    if studio:
        return studio

    # 2) minted onboard code (fallback for studios with no short name).
    studio = (
        db.query(Studio)
        .filter(func.upper(Studio.onboard_code) == code.upper(),
                Studio.is_active == True)
        .first()
    )
    if studio:
        return studio

    return None
