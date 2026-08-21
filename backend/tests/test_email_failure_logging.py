"""Outbound-email failures must be LOUD in the log — and still silent to the caller.

The scenario this guards against: `login_events` holds nothing but
`password_reset_requested / success=false / "email send failed"` because
`_send_reset_email_and_log` caught `Exception` and logged NOTHING, so the
provider's `535 Incorrect authentication data` never reached the container
log. The credential would be the bug; the silence is what lets it go
unnoticed.

These tests pin both halves of the fix:
  * the response is byte-identical whether or not the send blew up
    (`/api/auth/forgot-password` is public and enumeration-safe — see the long
    comments in app/routes/auth.py before changing anything here), and
  * the failure now appears at ERROR level, naming the feature and carrying the
    provider error, with no token or credential in the text.
"""
import logging

import pytest

from app.models.login_event import LoginEvent
from app.models.user import User
from app.utils.password import hash_password

RESET_URL = "/api/auth/forgot-password"


def _user(db, email, *, commit=False):
    u = User(email=email, name="Lane C", password_hash=hash_password("orig-pw-123"),
             role="instructor", is_active=True)
    db.add(u)
    # The audit row is written on its OWN connection (see services/login_audit.py),
    # so a merely-flushed user is invisible to it and its FK write fails. Tests
    # that assert on the persisted row must commit — and clean up after themselves.
    if commit:
        db.commit()
    else:
        db.flush()
    return u


@pytest.fixture
def committed_user(db):
    """A user that really exists on the DB, so the audit write (own connection,
    own transaction) can satisfy its FK — i.e. the prod-normal path. Rows are
    deleted at teardown because a commit escapes the fixture rollback."""
    created = []

    def _make(email):
        user = _user(db, email, commit=True)
        created.append((user.id, email))
        return user

    yield _make
    for user_id, email in created:
        db.query(LoginEvent).filter(LoginEvent.email_attempted == email).delete()
        db.query(User).filter(User.id == user_id).delete()
    db.commit()


def _raiser(exc):
    def _boom(*args, **kwargs):
        raise exc
    return _boom


def _smtp_auth_failure():
    """The real prod failure, verbatim from the provider probe."""
    import smtplib
    return smtplib.SMTPAuthenticationError(535, b"Incorrect authentication data")


# ── enumeration safety is unchanged ───────────────────────────────────────────

def test_send_failure_still_returns_the_generic_sent_true(client, db, monkeypatch):
    """The whole point of the swallow: a provider outage must not turn the
    matched-email branch into a 500 that unmatched emails never produce."""
    _user(db, "lane-c-generic@test.com")
    monkeypatch.setattr("app.services.email.send_reset_password_email",
                        _raiser(_smtp_auth_failure()))

    known = client.post(RESET_URL, json={"email": "lane-c-generic@test.com"})
    unknown = client.post(RESET_URL, json={"email": "lane-c-nobody@test.com"})

    assert known.status_code == 200
    assert known.json() == {"sent": True}
    assert known.json() == unknown.json()


# ── the failure is now visible ────────────────────────────────────────────────

def test_send_failure_is_logged_at_error_naming_the_feature(client, db, monkeypatch, caplog):
    _user(db, "lane-c-logged@test.com")
    monkeypatch.setattr("app.services.email.send_reset_password_email",
                        _raiser(_smtp_auth_failure()))

    with caplog.at_level(logging.ERROR, logger="app.auth"):
        resp = client.post(RESET_URL, json={"email": "lane-c-logged@test.com"})
    assert resp.status_code == 200

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR and r.name == "app.auth"]
    assert len(errors) == 1, f"expected one ERROR from app.auth, got {caplog.text!r}"
    message = errors[0].getMessage()
    # Names the feature (so a prod grep finds it) and the recipient (already in
    # login_events, so no new disclosure), and carries the provider's own error.
    assert "password reset email" in message
    assert "lane-c-logged@test.com" in message
    assert "SMTPAuthenticationError" in message
    assert "Incorrect authentication data" in message


def test_invite_send_failure_is_logged_and_still_raises(client, db, auth_headers, admin_user,
                                                        monkeypatch, caplog):
    """The invite path shares the mailbox and dies in the same outage. It does
    not swallow — the caller still gets the error — but it must say so in the log."""
    user = _user(db, "lane-c-invite@test.com")
    monkeypatch.setattr("app.services.email.send_invite_email",
                        _raiser(_smtp_auth_failure()))

    with caplog.at_level(logging.ERROR, logger="app.auth"):
        with pytest.raises(Exception):
            client.post("/api/auth/invite", headers=auth_headers,
                        json={"user_id": str(user.id)})

    messages = [r.getMessage() for r in caplog.records if r.name == "app.auth"]
    assert any("invite email FAILED" in m and "lane-c-invite@test.com" in m
               for m in messages), messages
    db.refresh(user)
    assert user.invite_sent_at is None  # nothing was sent, so nothing is marked


# ── the log line cannot carry a secret ────────────────────────────────────────

def test_log_never_contains_the_reset_token(client, committed_user, monkeypatch, caplog):
    """Worst case: a provider client that stringifies the request it sent, body
    and all. The reset link — hence a live password-reset token — is in that
    body. It must not survive into the log."""
    committed_user("lane-c-token@test.com")

    captured = {}

    def _boom(to, name, token):
        captured["token"] = token
        raise RuntimeError(
            f"POST https://api.example.com/emails failed: "
            f'{{"html": "<a href=\\"https://app/reset-password?token={token}\\">"}}'
        )

    monkeypatch.setattr("app.services.email.send_reset_password_email", _boom)

    with caplog.at_level(logging.ERROR, logger="app.auth"):
        resp = client.post(RESET_URL, json={"email": "lane-c-token@test.com"})

    assert resp.status_code == 200
    token = captured["token"]
    assert len(token) > 20  # a real JWT, not an empty string that would pass trivially
    auth_lines = [r.getMessage() for r in caplog.records if r.name == "app.auth"]
    assert any("[REDACTED]" in m for m in auth_lines), auth_lines
    assert all(token not in m for m in auth_lines)
    # And nothing else in the pipeline re-leaks it either. This is why the fix
    # does not attach exc_info: `logger.exception` re-renders the UNSCRUBBED
    # str(exc). (It also fails if a *downstream* handler logs a traceback while
    # this exception is still the active context — see the report note on
    # app/services/login_audit.py:60, which does exactly that when its own write
    # fails.)
    assert token not in caplog.text


def test_log_never_contains_the_smtp_password(client, committed_user, monkeypatch, caplog):
    """smtplib itself never puts the password in an exception, but the scrub is
    what makes that guaranteed rather than fortunate."""
    monkeypatch.setenv("SMTP_PASSWORD", "sup3r-s3cret-mailbox-pw")
    committed_user("lane-c-secret@test.com")
    monkeypatch.setattr(
        "app.services.email.send_reset_password_email",
        _raiser(RuntimeError("auth failed for user reply@example.com "
                             "with password sup3r-s3cret-mailbox-pw")),
    )

    with caplog.at_level(logging.ERROR, logger="app.auth"):
        client.post(RESET_URL, json={"email": "lane-c-secret@test.com"})

    assert "sup3r-s3cret-mailbox-pw" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_describe_send_failure_keeps_the_diagnosis_and_drops_the_secrets(monkeypatch):
    from app.services import email as email_service

    monkeypatch.setenv("RESEND_API_KEY", "re_live_abcdef123456")
    described = email_service.describe_send_failure(
        RuntimeError("401 Unauthorized (key re_live_abcdef123456)"),
        redact=("a-token-value-long-enough",),
    )
    assert described.startswith("RuntimeError: ")
    assert "401 Unauthorized" in described
    assert "re_live_abcdef123456" not in described

    described2 = email_service.describe_send_failure(
        RuntimeError("body contained a-token-value-long-enough"))
    assert "a-token-value-long-enough" in described2, (
        "only secrets the caller names are scrubbed — proves the previous "
        "assertion tested the redaction, not a coincidence")

    # An empty/short secret must not blank out the whole message.
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_PASSWORD", "")
    assert "Incorrect authentication data" in email_service.describe_send_failure(
        _smtp_auth_failure())


# ── the audit row still lands ─────────────────────────────────────────────────

def test_failed_send_still_writes_a_login_event_with_the_exception_type(client, db, committed_user,
                                                                       monkeypatch):
    email = "lane-c-audit@test.com"
    user = committed_user(email)
    monkeypatch.setattr("app.services.email.send_reset_password_email",
                        _raiser(_smtp_auth_failure()))

    resp = client.post(RESET_URL, json={"email": email})
    assert resp.status_code == 200

    rows = (db.query(LoginEvent)
            .filter(LoginEvent.email_attempted == email,
                    LoginEvent.event_type == "password_reset_requested")
            .all())
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].user_id == user.id
    # The type, never the message: this string is rendered on the admin Login
    # Log screen and must not be able to carry provider text.
    assert rows[0].detail == "email send failed: SMTPAuthenticationError"
    assert "Incorrect authentication data" not in (rows[0].detail or "")
