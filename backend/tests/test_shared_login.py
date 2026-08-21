"""Phase 1b — shared-device (group code + name + PIN) login.

Covers the PIN-set instructor listing, a successful login minting a SHORT-lived
studio-scoped token, and the generic-failure rejections (wrong PIN / wrong
studio / cross-studio user / unknown code).

No endpoint here commits, so the function-scoped rollback keeps the shared
test DB clean. PINs are set directly as hash_password('1234') per the task
guidance.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.studio import Studio
from app.models.user import User
from app.routes.auth import SHARED_SESSION_EXPIRE_MINUTES
from app.utils.password import hash_password
from app.utils.tokens import decode_token

STAMP = uuid4().hex[:8]
PIN = "1234"


def _studio(db, *, onboard_code):
    studio = Studio(name=f"Shared Studio {onboard_code}", display_name=f"Shared Studio {STAMP}",
                    onboard_code=onboard_code, is_active=True)
    db.add(studio)
    db.flush()
    return studio


def _instructor(db, studio, *, name, pin=PIN):
    user = User(
        email=f"shared-{uuid4().hex[:10]}@import.placeholder.local",
        name=name,
        password_hash=hash_password("unusable"),
        role="instructor",
        studio_id=studio.id,
        is_active=True,
        pin_hash=hash_password(pin) if pin else None,
    )
    db.add(user)
    db.flush()
    return user


# ── lookup ─────────────────────────────────────────────────────────────────

def test_shared_lookup_lists_only_pin_holders_no_secrets(client, db):
    studio = _studio(db, onboard_code=f"SL{STAMP[:4].upper()}")
    with_pin = _instructor(db, studio, name=f"Pinned {STAMP}")
    _instructor(db, studio, name=f"No Pin {STAMP}", pin=None)

    resp = client.post("/api/auth/shared/lookup", json={"studio_code": studio.onboard_code})
    assert resp.status_code == 200
    body = resp.json()
    assert body["studio"]["id"] == str(studio.id)
    assert [i["name"] for i in body["instructors"]] == [f"Pinned {STAMP}"]
    assert set(body["instructors"][0].keys()) == {"id", "name"}
    assert body["instructors"][0]["id"] == str(with_pin.id)


def test_shared_lookup_unknown_code_is_generic_404(client, db):
    resp = client.post("/api/auth/shared/lookup", json={"studio_code": f"MISSING{STAMP}"})
    assert resp.status_code == 404


# ── login ──────────────────────────────────────────────────────────────────

def test_shared_login_success_mints_short_studio_scoped_token(client, db):
    studio = _studio(db, onboard_code=f"OK{STAMP[:4].upper()}")
    instructor = _instructor(db, studio, name=f"Goodpin {STAMP}")

    resp = client.post("/api/auth/shared/login", json={
        "studio_code": studio.onboard_code, "user_id": str(instructor.id), "pin": PIN,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == str(instructor.id)
    assert body["access_token"]

    payload = decode_token(body["access_token"])
    assert payload["sub"] == str(instructor.id)
    assert payload["role"] == "instructor"
    assert payload["type"] == "access"
    # scoped to the studio
    assert payload["osid"] == str(studio.id)
    # short-lived: well under the default 12h access token
    exp = datetime.fromtimestamp(payload["exp"], timezone.utc)
    now = datetime.now(timezone.utc)
    assert exp <= now + timedelta(minutes=SHARED_SESSION_EXPIRE_MINUTES + 2)
    assert exp > now


def test_shared_login_wrong_pin_rejected_generically(client, db):
    studio = _studio(db, onboard_code=f"WP{STAMP[:4].upper()}")
    instructor = _instructor(db, studio, name=f"Wrongpin {STAMP}")
    resp = client.post("/api/auth/shared/login", json={
        "studio_code": studio.onboard_code, "user_id": str(instructor.id), "pin": "9999",
    })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect studio code, name, or PIN."


def test_shared_login_unknown_studio_rejected(client, db):
    studio = _studio(db, onboard_code=f"US{STAMP[:4].upper()}")
    instructor = _instructor(db, studio, name=f"Nostudio {STAMP}")
    resp = client.post("/api/auth/shared/login", json={
        "studio_code": f"NOSUCH{STAMP}", "user_id": str(instructor.id), "pin": PIN,
    })
    assert resp.status_code == 401


def test_shared_login_user_from_other_studio_rejected(client, db):
    studio_a = _studio(db, onboard_code=f"AA{STAMP[:4].upper()}")
    studio_b = _studio(db, onboard_code=f"BB{STAMP[:4].upper()}")
    # a valid instructor+PIN, but belonging to studio_b, cannot log in via A's code
    instructor_b = _instructor(db, studio_b, name=f"Bee {STAMP}")
    resp = client.post("/api/auth/shared/login", json={
        "studio_code": studio_a.onboard_code, "user_id": str(instructor_b.id), "pin": PIN,
    })
    assert resp.status_code == 401


def test_shared_login_instructor_without_pin_rejected(client, db):
    studio = _studio(db, onboard_code=f"NP{STAMP[:4].upper()}")
    instructor = _instructor(db, studio, name=f"Pinless {STAMP}", pin=None)
    resp = client.post("/api/auth/shared/login", json={
        "studio_code": studio.onboard_code, "user_id": str(instructor.id), "pin": PIN,
    })
    assert resp.status_code == 401
