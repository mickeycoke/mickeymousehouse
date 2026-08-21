"""Phase 1a — public, unauthenticated instructor self-serve onboarding.

Covers studio lookup (by short name or onboard code), the enumeration
guards, claiming an unclaimed instructor, the takeover/collision rejections,
the B-1 rate limits (failed-lookup per-IP, PIN per-IP AND per-target-user),
onboard-code generation on studio create, and the admin backfill endpoint.

Setup uses db.flush() (never commit) so nothing leaks into the shared test DB;
identifiers are stamped unique per run for the same reason. Exception: the
per-user lockout tests commit their fixtures — login-audit rows are written in
their OWN transaction (see app/services/login_audit.py), so a row carrying a
user_id FK is only recordable when the user row is actually committed.

Rate-limit tests set X-Forwarded-For to a stamped per-test pseudo-IP:
_client_ip() reads that header first, and unique fake IPs keep each test's
failure counter isolated from every other test (and from the shared default
"testclient" address).
"""
from datetime import datetime
from uuid import uuid4

from app.models.studio import Studio
from app.models.user import User
from app.utils.password import hash_password, hash_pin

STAMP = uuid4().hex[:8]


def _studio(db, *, onboard_code=None, name=None, active=True):
    studio = Studio(
        name=name or f"Onboard Studio {STAMP}-{uuid4().hex[:4]}",
        display_name=name or f"Onboard Studio {STAMP}",
        onboard_code=onboard_code,
        is_active=active,
    )
    db.add(studio)
    db.flush()
    return studio


def _instructor(db, studio, *, name, claimed=False, email=None, pin=None):
    user = User(
        email=email or f"onb-{uuid4().hex[:10]}@import.placeholder.local",
        name=name,
        password_hash=hash_password("unusable"),
        role="instructor",
        studio_id=studio.id,
        is_active=True,
        password_set_at=datetime.utcnow() if claimed else None,
        pin_hash=hash_pin(pin) if pin else None,
        pin=pin,
    )
    db.add(user)
    db.flush()
    return user


def _token_from_link(link):
    return link.split("token=", 1)[1]


# ── studio lookup ──────────────────────────────────────────────────────────

def test_lookup_by_onboard_code_lists_only_unclaimed_and_no_emails(client, db):
    studio = _studio(db, onboard_code=f"OCODE{STAMP[:2].upper()}")
    other = _studio(db, onboard_code=f"OTHER{STAMP[:2].upper()}")
    unclaimed = _instructor(db, studio, name=f"Unclaimed {STAMP}")
    _instructor(db, studio, name=f"Claimed {STAMP}", claimed=True)
    _instructor(db, other, name=f"Elsewhere {STAMP}")

    resp = client.post("/api/onboard/studio-lookup", json={"studio_code": studio.onboard_code})
    assert resp.status_code == 200
    body = resp.json()
    assert body["studio"]["id"] == str(studio.id)
    names = [i["name"] for i in body["instructors"]]
    assert names == [f"Unclaimed {STAMP}"]
    # id + name only — never email/role/pin
    assert set(body["instructors"][0].keys()) == {"id", "name"}
    assert str(unclaimed.id) == body["instructors"][0]["id"]


def test_lookup_is_case_insensitive_on_onboard_code(client, db):
    studio = _studio(db, onboard_code=f"CASE{STAMP[:2].upper()}A")
    _instructor(db, studio, name=f"Casey {STAMP}")
    resp = client.post("/api/onboard/studio-lookup",
                       json={"studio_code": studio.onboard_code.lower()})
    assert resp.status_code == 200
    assert resp.json()["studio"]["id"] == str(studio.id)


def test_lookup_by_short_name(client, db):
    studio = _studio(db)
    studio.short_name = f"SHORT{STAMP[:3].upper()}"
    db.flush()
    _instructor(db, studio, name=f"Shorty {STAMP}")

    resp = client.post("/api/onboard/studio-lookup", json={"studio_code": studio.short_name})
    assert resp.status_code == 200
    assert resp.json()["studio"]["id"] == str(studio.id)


def test_lookup_unknown_code_is_generic_404(client, db):
    resp = client.post("/api/onboard/studio-lookup", json={"studio_code": f"NOPE{STAMP}"})
    assert resp.status_code == 404
    # generic — no hint whether the studio or its instructors were the miss
    assert "studio" in resp.json()["detail"].lower()


def test_lookup_ignores_inactive_studio(client, db):
    studio = _studio(db, onboard_code=f"INACT{STAMP[:2].upper()}", active=False)
    resp = client.post("/api/onboard/studio-lookup", json={"studio_code": studio.onboard_code})
    assert resp.status_code == 404


# ── rate limiting (B-1) ────────────────────────────────────────────────────

def _ip(tag):
    """A unique fake client address per test — see the module docstring."""
    return {"X-Forwarded-For": f"{tag}-{STAMP}"}


def test_failed_lookups_locked_out_per_ip_after_ten(client, db):
    studio = _studio(db, onboard_code=f"RLIM{STAMP[:2].upper()}")
    hdrs = _ip("lk-limit")

    for n in range(5):
        r = client.post("/api/onboard/studio-lookup",
                        json={"studio_code": f"MISS{STAMP}{n}"}, headers=hdrs)
        assert r.status_code == 404

    # a SUCCESSFUL lookup between failures does not count toward the limit
    ok = client.post("/api/onboard/studio-lookup",
                     json={"studio_code": studio.onboard_code}, headers=hdrs)
    assert ok.status_code == 200

    for n in range(5, 10):
        r = client.post("/api/onboard/studio-lookup",
                        json={"studio_code": f"MISS{STAMP}{n}"}, headers=hdrs)
        assert r.status_code == 404

    # 11th miss: locked out — and the check runs BEFORE the code is resolved,
    # so even a valid code is refused from this IP now
    r = client.post("/api/onboard/studio-lookup",
                    json={"studio_code": f"MISS{STAMP}X"}, headers=hdrs)
    assert r.status_code == 429
    r = client.post("/api/onboard/studio-lookup",
                    json={"studio_code": studio.onboard_code}, headers=hdrs)
    assert r.status_code == 429


def test_lookup_lockout_is_per_ip(client, db):
    studio = _studio(db, onboard_code=f"RLIP{STAMP[:2].upper()}")
    hdrs = _ip("lk-iso-a")
    for n in range(10):
        client.post("/api/onboard/studio-lookup",
                    json={"studio_code": f"ISOMISS{STAMP}{n}"}, headers=hdrs)
    assert client.post("/api/onboard/studio-lookup",
                       json={"studio_code": f"ISOMISS{STAMP}Z"},
                       headers=hdrs).status_code == 429

    # a different address still gets normal behaviour: 404 on a miss, 200 on a hit
    other = _ip("lk-iso-b")
    assert client.post("/api/onboard/studio-lookup",
                       json={"studio_code": f"ISOMISS{STAMP}Z"},
                       headers=other).status_code == 404
    assert client.post("/api/onboard/studio-lookup",
                       json={"studio_code": studio.onboard_code},
                       headers=other).status_code == 200


def test_pin_lockout_is_per_target_user_across_ips(client, db):
    studio = _studio(db, onboard_code=f"PLCK{STAMP[:2].upper()}")
    target = _instructor(db, studio, name=f"Target {STAMP}", pin="7311")
    bystander = _instructor(db, studio, name=f"Bystander {STAMP}", pin="9922")
    db.commit()  # audit rows carry user_id FKs — see the module docstring

    # three wrong PINs against ONE user, each from a DIFFERENT address, so no
    # single IP ever reaches its own 3-failure limit
    for n in range(3):
        r = client.post("/api/onboard/verify-pin",
                        json={"user_id": str(target.id), "pin": "0000"},
                        headers=_ip(f"pin-user-{n}"))
        assert r.status_code == 401

    # 4th attempt from yet another fresh IP — even with the CORRECT pin — is
    # refused by the per-user counter
    r = client.post("/api/onboard/verify-pin",
                    json={"user_id": str(target.id), "pin": "7311"},
                    headers=_ip("pin-user-x"))
    assert r.status_code == 429

    # a different user is unaffected
    ok = client.post("/api/onboard/verify-pin",
                     json={"user_id": str(bystander.id), "pin": "9922"},
                     headers=_ip("pin-user-y"))
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_pin_lockout_per_ip_still_applies(client, db):
    """The pre-existing per-IP axis: one address burning its 3 failures across
    DIFFERENT users is locked out, while the users themselves stay reachable
    from elsewhere."""
    studio = _studio(db, onboard_code=f"PIPS{STAMP[:2].upper()}")
    users = [_instructor(db, studio, name=f"PerIp {n} {STAMP}", pin="4411")
             for n in range(3)]
    db.commit()

    hdrs = _ip("pin-ip-a")
    for u in users:
        r = client.post("/api/onboard/verify-pin",
                        json={"user_id": str(u.id), "pin": "0000"}, headers=hdrs)
        assert r.status_code == 401

    r = client.post("/api/onboard/verify-pin",
                    json={"user_id": str(users[0].id), "pin": "0000"}, headers=hdrs)
    assert r.status_code == 429

    # each user only accumulated ONE failure, so from a fresh IP they are fine
    ok = client.post("/api/onboard/verify-pin",
                     json={"user_id": str(users[0].id), "pin": "4411"},
                     headers=_ip("pin-ip-b"))
    assert ok.status_code == 200


# ── claim ──────────────────────────────────────────────────────────────────

def test_claim_sets_email_sends_invite_and_activates(client, db):
    studio = _studio(db, onboard_code=f"CLAIM{STAMP[:2].upper()}")
    instructor = _instructor(db, studio, name=f"Claimer {STAMP}", pin="4471")

    email = f"claimer-{STAMP}@real.example.com"
    resp = client.post("/api/onboard/claim",
                       json={"user_id": str(instructor.id), "pin": "4471", "email": email})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is True
    assert body["email"] == email
    assert body["invite_link"]  # console backend in dev

    db.refresh(instructor)
    assert instructor.email == email
    assert instructor.invite_sent_at is not None

    # the emailed link drives the normal Phase 0 set-password -> activation
    token = _token_from_link(body["invite_link"])
    done = client.post("/api/auth/set-password", json={"token": token, "password": "s3cret-pw!!"})
    assert done.status_code == 200
    db.refresh(instructor)
    assert instructor.password_set_at is not None

    # now claimed: no longer offered by lookup
    again = client.post("/api/onboard/studio-lookup", json={"studio_code": studio.onboard_code})
    assert str(instructor.id) not in [i["id"] for i in again.json()["instructors"]]


def test_claim_normalizes_email_case(client, db):
    studio = _studio(db, onboard_code=f"NORM{STAMP[:2].upper()}A")
    instructor = _instructor(db, studio, name=f"Norma {STAMP}", pin="8823")
    resp = client.post("/api/onboard/claim",
                       json={"user_id": str(instructor.id), "pin": "8823", "email": f"MixedCase-{STAMP}@Ex.COM"})
    assert resp.status_code == 200
    db.refresh(instructor)
    assert instructor.email == f"mixedcase-{STAMP}@ex.com"


def test_claim_rejects_already_claimed_instructor(client, db):
    studio = _studio(db, onboard_code=f"DBL{STAMP[:2].upper()}AA")
    instructor = _instructor(db, studio, name=f"Taken {STAMP}", claimed=True)
    # An already-claimed instructor is rejected before the PIN is even
    # checked (claimability is resolved first) — the PIN value here is a
    # placeholder, never verified.
    resp = client.post("/api/onboard/claim",
                       json={"user_id": str(instructor.id), "pin": "0000", "email": f"taken-{STAMP}@ex.com"})
    assert resp.status_code == 404  # generic — same as an unknown user


def test_claim_rejects_email_already_in_use(client, db):
    studio = _studio(db, onboard_code=f"INUSE{STAMP[:1].upper()}")
    existing_email = f"existing-{STAMP}@ex.com"
    _instructor(db, studio, name=f"Existing {STAMP}", email=existing_email)
    # PIN verification runs before the email-collision check, so this
    # instructor needs a real, matching PIN to reach it.
    instructor = _instructor(db, studio, name=f"Wants Email {STAMP}", pin="5541")

    resp = client.post("/api/onboard/claim",
                       json={"user_id": str(instructor.id), "pin": "5541", "email": existing_email})
    assert resp.status_code == 400
    assert "already in use" in resp.json()["detail"].lower()


def test_claim_rejects_unknown_user(client, db):
    resp = client.post("/api/onboard/claim",
                       json={"user_id": str(uuid4()), "pin": "0000", "email": f"ghost-{STAMP}@ex.com"})
    assert resp.status_code == 404


def test_claim_rejects_non_instructor(client, db):
    studio = _studio(db, onboard_code=f"ROLE{STAMP[:2].upper()}")
    manager = User(
        email=f"mgr-{STAMP}@import.placeholder.local", name=f"Manny {STAMP}",
        password_hash=hash_password("unusable"), role="manager",
        studio_id=studio.id, is_active=True,
    )
    db.add(manager)
    db.flush()
    resp = client.post("/api/onboard/claim",
                       json={"user_id": str(manager.id), "pin": "0000", "email": f"mgr-real-{STAMP}@ex.com"})
    assert resp.status_code == 404


# ── onboard-code generation ────────────────────────────────────────────────

def test_create_studio_auto_assigns_onboard_code(client, auth_headers, db):
    resp = client.post("/api/studios", headers=auth_headers,
                       json={"name": f"Auto Code Studio {STAMP}"})
    assert resp.status_code == 201
    code = resp.json()["onboard_code"]
    assert code and len(code) == 6
    # the fresh code resolves via lookup
    look = client.post("/api/onboard/studio-lookup", json={"studio_code": code})
    assert look.status_code == 200
    assert look.json()["studio"]["id"] == resp.json()["id"]


def test_backfill_onboard_codes_is_idempotent_and_admin_only(client, auth_headers, db):
    s1 = _studio(db, onboard_code=None)
    s2 = _studio(db, onboard_code=None)
    assert s1.onboard_code is None and s2.onboard_code is None

    # non-admin cannot backfill
    plain = User(email=f"plain-{STAMP}@ex.com", name="Plain",
                 password_hash=hash_password("password123"), role="instructor", is_active=True)
    db.add(plain)
    db.flush()
    plain_token = client.post("/api/auth/login",
                              json={"email": plain.email, "password": "password123"}).json()["access_token"]
    forbidden = client.post("/api/studios/backfill-onboard-codes",
                            headers={"Authorization": f"Bearer {plain_token}"})
    assert forbidden.status_code == 403

    first = client.post("/api/studios/backfill-onboard-codes", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["assigned"] >= 2
    db.refresh(s1)
    db.refresh(s2)
    assert s1.onboard_code and s2.onboard_code
    assert s1.onboard_code != s2.onboard_code

    # re-running assigns nothing
    second = client.post("/api/studios/backfill-onboard-codes", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["assigned"] == 0


# ---------------------------------------------------------------------------
# Case-insensitive instructor PIN. PINs are matched
# case-insensitively — stored lowercased via hash_pin, normalized at verify.
# ---------------------------------------------------------------------------

def test_pin_is_case_insensitive_via_verify_pin(client, db):
    from app.utils.password import verify_pin, hash_pin, normalize_pin
    # Unit level: a hash of a mixed-case PIN accepts any casing.
    stored = hash_pin("AbCd")
    assert verify_pin("abcd", stored)
    assert verify_pin("ABCD", stored)
    assert verify_pin("aBcD", stored)
    assert not verify_pin("abce", stored)
    assert normalize_pin("AbCd") == "abcd"

    # HTTP level: instructor stored with a mixed-case PIN, verified with a
    # differently-cased input through the real endpoint.
    studio = _studio(db, onboard_code=f"CI{STAMP}")
    instructor = _instructor(db, studio, name=f"Casey {STAMP}", pin="AbCd")
    db.commit()  # verify-pin path records a login_events row carrying user_id
    try:
        r = client.post("/api/onboard/verify-pin",
                        json={"user_id": str(instructor.id), "pin": "abcd"},
                        headers={"X-Forwarded-For": f"pin-ci-{STAMP}"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
    finally:
        db.query(User).filter(User.id == instructor.id).delete()
        db.query(Studio).filter(Studio.id == studio.id).delete()
        db.commit()


# ---------------------------------------------------------------------------
# Onboarding email branching. verify-pin exposes a single
# needs_setup bit (placeholder vs real email); claim() accepts an optional
# password for a one-step combined setup, and rejects real-email instructors
# outright.
# ---------------------------------------------------------------------------

def test_verify_pin_needs_setup_true_for_placeholder_email(client, db):
    studio = _studio(db, onboard_code=f"NS{STAMP[:3].upper()}A")
    instructor = _instructor(db, studio, name=f"Placeholder {STAMP}", pin="3001",
                             email=f"trainer-x-{STAMP}@import.placeholder.local")
    resp = client.post("/api/onboard/verify-pin",
                       json={"user_id": str(instructor.id), "pin": "3001"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "needs_setup": True}


def test_verify_pin_needs_setup_true_for_bulk_import_placeholder(client, db):
    studio = _studio(db, onboard_code=f"NS{STAMP[:3].upper()}B")
    instructor = _instructor(db, studio, name=f"BulkImport {STAMP}", pin="3002",
                             email="bulk-import@import.placeholder.local")
    resp = client.post("/api/onboard/verify-pin",
                       json={"user_id": str(instructor.id), "pin": "3002"})
    assert resp.status_code == 200
    assert resp.json()["needs_setup"] is True


def test_verify_pin_needs_setup_true_for_no_email(client, db):
    studio = _studio(db, onboard_code=f"NS{STAMP[:3].upper()}C")
    instructor = _instructor(db, studio, name=f"NoEmail {STAMP}", pin="3003")
    instructor.email = None
    db.flush()
    resp = client.post("/api/onboard/verify-pin",
                       json={"user_id": str(instructor.id), "pin": "3003"})
    assert resp.status_code == 200
    assert resp.json()["needs_setup"] is True


def test_verify_pin_needs_setup_false_for_real_email(client, db):
    studio = _studio(db, onboard_code=f"NS{STAMP[:3].upper()}D")
    instructor = _instructor(db, studio, name=f"RealEmail {STAMP}", pin="3004",
                             email=f"jane-{STAMP}@example.com")
    resp = client.post("/api/onboard/verify-pin",
                       json={"user_id": str(instructor.id), "pin": "3004"})
    assert resp.status_code == 200
    assert resp.json()["needs_setup"] is False


def test_verify_pin_wrong_pin_body_has_no_needs_setup_key(client, db):
    studio = _studio(db, onboard_code=f"NS{STAMP[:3].upper()}E")
    instructor = _instructor(db, studio, name=f"WrongPin {STAMP}", pin="3005")
    resp = client.post("/api/onboard/verify-pin",
                       json={"user_id": str(instructor.id), "pin": "9999"})
    assert resp.status_code == 401
    assert "needs_setup" not in resp.json()


def test_is_placeholder_email_suffix_boundary_conditions():
    from app.routes.onboard import _is_placeholder_email
    # the '@' anchor matters -- a lookalike domain is a REAL email
    assert _is_placeholder_email("x@evil-import.placeholder.local") is False
    # endswith, not contains -- a suffix tacked onto the placeholder is REAL
    assert _is_placeholder_email("x@import.placeholder.local.attacker.com") is False
    # case-insensitive
    assert _is_placeholder_email("X@IMPORT.PLACEHOLDER.LOCAL") is True
    # empty / None
    assert _is_placeholder_email("") is True
    assert _is_placeholder_email(None) is True
    # ordinary real email
    assert _is_placeholder_email("real@example.com") is False


def test_claim_combined_mode_activates_and_logs_in(client, db):
    studio = _studio(db, onboard_code=f"CMB{STAMP[:2].upper()}A")
    instructor = _instructor(db, studio, name=f"Combined {STAMP}", pin="4001",
                             email=f"trainer-y-{STAMP}@import.placeholder.local")
    email = f"combined-{STAMP}@real.example.com"
    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "4001", "email": email,
        "password": "s3cret-combined!!",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"sent": False, "email": email, "invite_link": None, "activated": True}

    db.refresh(instructor)
    assert instructor.email == email
    assert instructor.password_set_at is not None
    assert instructor.invite_sent_at is None  # no magic-link invite fired

    # end-to-end proof: the new credentials actually work
    login = client.post("/api/auth/login", json={"email": email, "password": "s3cret-combined!!"})
    assert login.status_code == 200, login.text

    # now claimed: no longer offered by lookup
    again = client.post("/api/onboard/studio-lookup", json={"studio_code": studio.onboard_code})
    assert str(instructor.id) not in [i["id"] for i in again.json()["instructors"]]


def test_claim_combined_mode_short_password_is_422(client, db):
    studio = _studio(db, onboard_code=f"CMB{STAMP[:2].upper()}B")
    instructor = _instructor(db, studio, name=f"ShortPw {STAMP}", pin="4002")
    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "4002",
        "email": f"shortpw-{STAMP}@ex.com", "password": "short",
    })
    assert resp.status_code == 422


def test_claim_combined_mode_rejects_email_already_in_use(client, db):
    studio = _studio(db, onboard_code=f"CMB{STAMP[:2].upper()}C")
    existing_email = f"combo-existing-{STAMP}@ex.com"
    _instructor(db, studio, name=f"ComboExisting {STAMP}", email=existing_email)
    instructor = _instructor(db, studio, name=f"ComboWants {STAMP}", pin="4003")

    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "4003",
        "email": existing_email, "password": "s3cret-combined!!",
    })
    assert resp.status_code == 400
    assert "already in use" in resp.json()["detail"].lower()


def test_claim_combined_mode_already_claimed_is_generic_404(client, db):
    studio = _studio(db, onboard_code=f"CMB{STAMP[:2].upper()}D")
    instructor = _instructor(db, studio, name=f"AlreadyClaimed {STAMP}", claimed=True)
    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "0000",
        "email": f"whatever-{STAMP}@ex.com", "password": "s3cret-combined!!",
    })
    assert resp.status_code == 404


def test_claim_rejects_real_email_instructor_with_password(client, db):
    studio = _studio(db, onboard_code=f"REJ{STAMP[:2].upper()}A")
    instructor = _instructor(db, studio, name=f"RealCombo {STAMP}", pin="4004",
                             email=f"realcombo-{STAMP}@example.com")
    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "4004",
        "email": f"newattempt-{STAMP}@ex.com", "password": "s3cret-combined!!",
    })
    assert resp.status_code == 409
    assert "forgot password" in resp.json()["detail"].lower()

    # nothing changed -- the email on file is untouched
    db.refresh(instructor)
    assert instructor.email == f"realcombo-{STAMP}@example.com"
    assert instructor.password_set_at is None


def test_claim_rejects_real_email_instructor_without_password_too(client, db):
    """The owner's rule is 'no new-account setup happens' once a real email
    exists -- that applies to the LEGACY magic-link mode too, not just the
    combined mode. The current UI never routes a real-email instructor here,
    so a request that reaches this branch is a direct API caller."""
    studio = _studio(db, onboard_code=f"REJ{STAMP[:2].upper()}B")
    instructor = _instructor(db, studio, name=f"RealLegacy {STAMP}", pin="4005",
                             email=f"reallegacy-{STAMP}@example.com")
    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "4005",
        "email": f"newattempt2-{STAMP}@ex.com",
    })
    assert resp.status_code == 409
    assert "forgot password" in resp.json()["detail"].lower()


def test_claim_combined_mode_respects_pin_lockout(client, db):
    studio = _studio(db, onboard_code=f"LCK{STAMP[:2].upper()}A")
    instructor = _instructor(db, studio, name=f"LockedCombo {STAMP}", pin="4006")
    db.commit()  # per-user lockout counter needs the row committed
    hdrs = {"X-Forwarded-For": f"combo-lock-{STAMP}"}

    for _ in range(3):
        client.post("/api/onboard/claim", json={
            "user_id": str(instructor.id), "pin": "0000",
            "email": f"lockedcombo-{STAMP}@ex.com", "password": "s3cret-combined!!",
        }, headers=hdrs)

    resp = client.post("/api/onboard/claim", json={
        "user_id": str(instructor.id), "pin": "4006",  # correct PIN, still locked
        "email": f"lockedcombo-{STAMP}@ex.com", "password": "s3cret-combined!!",
    }, headers=hdrs)
    assert resp.status_code == 429

    db.refresh(instructor)
    assert instructor.password_set_at is None  # lockout wins even with the right PIN
