"""Idempotent demo data for a fresh mickeymouse-house checkout.

Creates (or updates in place, if already present):
  * an admin login                  admin@example.com / admin123
  * a franchise                     "Demo Franchise"
  * a studio under that franchise   "Demo Studio", short code DEMO1 — the
                                     code /api/onboard/studio-lookup and
                                     /api/auth/shared/lookup resolve
  * a demo instructor at that studio, with a shared-device PIN of 1234, so
    the shared-device / onboarding login flow demos out of the box with no
    client data of any kind
  * a pricing tier                  "Sample Product"
  * one active announcement so the login "Notes to users" flow demos too

Safe to run repeatedly against the same database — every row is looked up
by its natural key first and only created if missing; an existing row is
left as found rather than duplicated.

Usage:
    python scripts/seed_demo.py
"""
import os
import sys
import uuid

# Make `app` importable when run as `python scripts/seed_demo.py` from the
# backend/ directory (the normal invocation) as well as from elsewhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.franchise import Franchise
from app.models.franchise_studio import FranchiseStudio
from app.models.pricing_tier import PricingTier
from app.models.studio import Studio
from app.models.user import User
from app.models.user_note import UserNote
from app.utils.backend_user import get_backend_user
from app.utils.password import hash_password, hash_pin

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"
FRANCHISE_NAME = "Demo Franchise"
STUDIO_NAME = "Demo Studio"
STUDIO_SHORT_CODE = "DEMO1"
INSTRUCTOR_EMAIL = "instructor@example.com"
INSTRUCTOR_PIN = "1234"
PRICING_TIER_NAME = "Sample Product"
WELCOME_NOTE_BODY = "Welcome to Mickeymouse House"


def _get_or_create_admin(db) -> User:
    user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if user is None:
        user = User(
            email=ADMIN_EMAIL,
            name="Admin",
            password_hash=hash_password(ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.flush()
        print(f"created admin user {ADMIN_EMAIL}")
    else:
        # Keep the demo password authoritative on re-run, in case someone
        # changed it while poking around.
        user.password_hash = hash_password(ADMIN_PASSWORD)
        user.role = "admin"
        user.is_active = True
        print(f"admin user {ADMIN_EMAIL} already exists — reset password")
    return user


def _get_or_create_franchise(db) -> Franchise:
    franchise = db.query(Franchise).filter(Franchise.name == FRANCHISE_NAME).first()
    if franchise is None:
        franchise = Franchise(name=FRANCHISE_NAME, is_active=True)
        db.add(franchise)
        db.flush()
        print(f"created franchise {FRANCHISE_NAME!r}")
    else:
        print(f"franchise {FRANCHISE_NAME!r} already exists")
    return franchise


def _get_or_create_studio(db, franchise: Franchise) -> Studio:
    studio = db.query(Studio).filter(Studio.name == STUDIO_NAME).first()
    if studio is None:
        studio = Studio(
            name=STUDIO_NAME,
            display_name=STUDIO_NAME,
            short_name=STUDIO_SHORT_CODE,
            is_active=True,
        )
        db.add(studio)
        db.flush()
        print(f"created studio {STUDIO_NAME!r} (code {STUDIO_SHORT_CODE})")
    else:
        studio.short_name = STUDIO_SHORT_CODE
        studio.is_active = True
        print(f"studio {STUDIO_NAME!r} already exists")

    link = (
        db.query(FranchiseStudio)
        .filter(FranchiseStudio.franchise_id == franchise.id, FranchiseStudio.studio_id == studio.id)
        .first()
    )
    if link is None:
        db.add(FranchiseStudio(franchise_id=franchise.id, studio_id=studio.id, is_active=True))
        print(f"linked {STUDIO_NAME!r} to {FRANCHISE_NAME!r}")
    elif not link.is_active:
        link.is_active = True
        print(f"re-activated {STUDIO_NAME!r}'s link to {FRANCHISE_NAME!r}")
    return studio


def _get_or_create_instructor(db, studio: Studio) -> User:
    user = db.query(User).filter(User.email == INSTRUCTOR_EMAIL).first()
    if user is None:
        user = User(
            email=INSTRUCTOR_EMAIL,
            name="Demo Instructor",
            password_hash=hash_password(uuid.uuid4().hex),  # unusable password; PIN is the real login
            role="instructor",
            studio_id=studio.id,
            pin=INSTRUCTOR_PIN,
            pin_hash=hash_pin(INSTRUCTOR_PIN),
            is_active=True,
        )
        db.add(user)
        db.flush()
        print(f"created instructor {INSTRUCTOR_EMAIL} at {STUDIO_NAME!r} with PIN {INSTRUCTOR_PIN}")
    else:
        user.studio_id = studio.id
        user.pin = INSTRUCTOR_PIN
        user.pin_hash = hash_pin(INSTRUCTOR_PIN)
        user.is_active = True
        print(f"instructor {INSTRUCTOR_EMAIL} already exists — PIN reset to {INSTRUCTOR_PIN}")
    return user


def _get_or_create_pricing_tier(db) -> PricingTier:
    tier = db.query(PricingTier).filter(PricingTier.name == PRICING_TIER_NAME).first()
    if tier is None:
        tier = PricingTier(
            name=PRICING_TIER_NAME,
            min_clients=0,
            max_clients=None,
            monthly_price_cents=2900,
            display_order=1,
            is_active=True,
        )
        db.add(tier)
        db.flush()
        print(f"created pricing tier {PRICING_TIER_NAME!r} ($29.00/mo)")
    else:
        print(f"pricing tier {PRICING_TIER_NAME!r} already exists")
    return tier


def _get_or_create_welcome_note(db) -> UserNote:
    note = db.query(UserNote).filter(UserNote.body == WELCOME_NOTE_BODY).first()
    if note is None:
        note = UserNote(
            body=WELCOME_NOTE_BODY,
            is_active=True,
            created_by_user_id=get_backend_user(db).id,
        )
        db.add(note)
        db.flush()
        print(f"created announcement {WELCOME_NOTE_BODY!r}")
    else:
        note.is_active = True
        print(f"announcement {WELCOME_NOTE_BODY!r} already exists")
    return note


def main() -> None:
    db = SessionLocal()
    try:
        _get_or_create_admin(db)
        franchise = _get_or_create_franchise(db)
        studio = _get_or_create_studio(db, franchise)
        _get_or_create_instructor(db, studio)
        _get_or_create_pricing_tier(db)
        _get_or_create_welcome_note(db)
        db.commit()
        print("\nDemo data ready.")
        print(f"  admin login:      {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print(f"  studio code:      {STUDIO_SHORT_CODE} (Demo Studio)")
        print(f"  instructor PIN:   {INSTRUCTOR_PIN} (Demo Instructor, via shared-device login)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
