import jwt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

# The default secret is fine for dev/tests but is public knowledge — anyone could
# forge tokens. Refuse to boot in production with it; warn everywhere else.
if SECRET == "dev-secret":
    # `is_production()` checks APP_ENV *and* ENVIRONMENT — this guard used to
    # read only ENVIRONMENT, which production never sets (it sets APP_ENV), so
    # it could never actually fire there. See utils/env.py.
    from app.utils.env import is_production
    if is_production():
        raise RuntimeError("JWT_SECRET must be set in production — refusing to start with the 'dev-secret' default.")
    import logging
    logging.getLogger("app.tokens").warning(
        "JWT_SECRET is the insecure default 'dev-secret' — OK for dev/tests, but MUST be set in production."
    )


def create_access_token(user_id: str, role: str, operating_studio_id: str | None = None,
                        impersonated_by: str | None = None) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_MINUTES),
    }
    # An admin impersonating an instructor bakes the operating studio in here, so
    # the impersonated (non-admin) session stays scoped to that one studio even
    # though the admin-only X-Studio-Id header is ignored for non-admins.
    if operating_studio_id:
        payload["osid"] = operating_studio_id
    # Impersonation tokens carry the driving admin's id (`act`, after RFC 8693's
    # actor claim). Endpoints use it to keep per-user state (note dismissals)
    # untouched — an impersonated session must never write "the user saw this".
    if impersonated_by:
        payload["act"] = impersonated_by
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure."""
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])


# Invite / magic-link tokens (Phase 0). A distinct `type` so an invite can
# never be used as an access token. `iat` is the single-use anchor: once the
# user's password_set_at passes the token's iat, the link is dead.
INVITE_EXPIRE_HOURS = int(os.getenv("INVITE_TOKEN_EXPIRE_HOURS", "72"))


def create_invite_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "invite",
        "iat": now,
        "exp": now + timedelta(hours=INVITE_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_invite_token(token: str) -> dict:
    """Decode + assert it is an invite token. Raises on expiry/invalid/type."""
    payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    if payload.get("type") != "invite":
        raise jwt.InvalidTokenError("not an invite token")
    return payload


# ── Password reset tokens (self-service "forgot my password") ────────────
# Same shape as an invite token — distinct `type`, `iat` single-use anchor —
# but a short, live-request expiry: this is "I forgot my password right now",
# not a 72h onboarding link.
RESET_EXPIRE_MINUTES = int(os.getenv("RESET_TOKEN_EXPIRE_MINUTES", "60"))


def create_reset_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "reset",
        "iat": now,
        "exp": now + timedelta(minutes=RESET_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_reset_token(token: str) -> dict:
    """Decode + assert it is a reset token. Raises on expiry/invalid/type."""
    payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    if payload.get("type") != "reset":
        raise jwt.InvalidTokenError("not a reset token")
    return payload


