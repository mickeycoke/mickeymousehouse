"""Pluggable transactional email (Phase 0).

The whole magic-link onboarding rides on this. In dev/tests the default
`console` backend just logs the message (and set-password responses surface
the link), so the full flow works with no provider account. Set
EMAIL_BACKEND=resend (or smtp) + the matching secrets to send for real —
no code change needed.
"""
import base64
import logging
import os
import re
import smtplib
from email.message import EmailMessage

import httpx

logger = logging.getLogger("app.email")

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/")
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console").lower()
EMAIL_FROM = os.getenv("EMAIL_FROM", "Mickeymouse House <no-reply@example.com>")


def is_live() -> bool:
    """True when emails actually leave the building (not the console backend)."""
    return EMAIL_BACKEND != "console"


def invite_link(token: str) -> str:
    return f"{APP_BASE_URL}/set-password?token={token}"


def reset_password_link(token: str) -> str:
    return f"{APP_BASE_URL}/reset-password?token={token}"


def _text_from_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def send_email(
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> dict:
    """Send one email via the configured backend. Raises on provider failure.

    `attachments` is a list of (filename, content_bytes, mime_type), for a
    caller that needs to attach a file to the message.
    """
    text = text or _text_from_html(html)
    attachments = attachments or []

    if EMAIL_BACKEND == "console":
        names = ", ".join(a[0] for a in attachments)
        logger.info(
            "EMAIL (console)\n  to: %s\n  subject: %s\n  attachments: %s\n  %s",
            to, subject, names or "(none)", text,
        )
        return {"backend": "console", "attachments": [a[0] for a in attachments]}

    if EMAIL_BACKEND == "resend":
        key = os.environ["RESEND_API_KEY"]
        payload = {"from": EMAIL_FROM, "to": [to], "subject": subject, "html": html, "text": text}
        if attachments:
            payload["attachments"] = [
                {"filename": name, "content": base64.b64encode(content).decode("ascii")}
                for name, content, _mime in attachments
            ]
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return {"backend": "resend", "id": resp.json().get("id")}

    if EMAIL_BACKEND == "smtp":
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = EMAIL_FROM, to, subject
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        for name, content, mime in attachments:
            maintype, _, subtype = mime.partition("/")
            msg.add_attachment(content, maintype=maintype or "application",
                               subtype=subtype or "octet-stream", filename=name)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
            if smtp_user:
                s.login(smtp_user, os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
        return {"backend": "smtp"}

    raise RuntimeError(f"Unknown EMAIL_BACKEND: {EMAIL_BACKEND!r}")


def describe_send_failure(exc: BaseException, *, redact: tuple[str, ...] = ()) -> str:
    """A one-line, log-SAFE description of a failed send: exception type + the
    provider's own message.

    Why the message is kept: it is the only thing that says WHY outbound mail is
    down. A bare `535 Incorrect authentication data` from the SMTP host is
    otherwise invisible if the caller swallows the exception and logs nothing.

    Why it is scrubbed first: the message is provider-controlled text, and some
    clients stringify the request they sent. So every configured credential, plus
    any secret the caller names in `redact` (e.g. the reset token, which lives in
    the message body), is replaced before the string can reach a log file.

    Deliberately returns a string rather than logging: the caller owns the log
    line, and no traceback is attached anywhere — `exc_info` would re-render the
    UNSCRUBBED `str(exc)` and defeat the redaction above.
    """
    text = " ".join(str(exc).split())
    secrets = [os.getenv("SMTP_PASSWORD") or "", os.getenv("RESEND_API_KEY") or ""]
    secrets.extend(redact)
    for secret in secrets:
        # Short values are skipped: a 2-character "password" would blank out
        # half the message and tell us nothing.
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[REDACTED]")
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _reset_expiry_text() -> str:
    from app.utils.tokens import RESET_EXPIRE_MINUTES
    if RESET_EXPIRE_MINUTES % 60 == 0:
        hours = RESET_EXPIRE_MINUTES // 60
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{RESET_EXPIRE_MINUTES} minutes"


def send_reset_password_email(to: str, name: str, token: str) -> str:
    """Send the self-service password reset link. Returns the link (handy in
    dev/console visibility, same convention as send_invite_email)."""
    link = reset_password_link(token)
    subject = "Reset your Mickeymouse House password"
    expiry = _reset_expiry_text()
    html = (
        f"<p>Hi {name or 'there'},</p>"
        f"<p>We got a request to reset your Mickeymouse House password.</p>"
        f"<p><a href=\"{link}\">Choose a new password</a> to continue.</p>"
        f"<p style=\"color:#888;font-size:13px\">This link expires in {expiry}. "
        f"If you didn't request this, you can safely ignore this email — your "
        f"password won't change. If the button doesn't work, paste this into "
        f"your browser:<br>{link}</p>"
    )
    send_email(to, subject, html)
    return link


def send_billing_checkout_email(
    to: str, studio_name: str, tier_name: str | None, monthly_cost_display: str, checkout_url: str,
) -> str:
    """Email a studio's contact their subscription checkout link (admin
    "Send Checkout Link") — states the pricing tier (if any) and
    the monthly cost, then a button to pay through Stripe. Returns the subject
    line. The recipient pays via the hosted Stripe Checkout page; status flips
    only from the resulting webhook, never this email."""
    tier_line = (
        f"<li>Plan: <strong>{tier_name}</strong></li>" if tier_name else ""
    )
    subject = f"Set up billing for {studio_name} — Mickeymouse House"
    html = (
        f"<p>Hi there,</p>"
        f"<p>Here are the billing details for <strong>{studio_name}</strong>:</p>"
        f"<ul>{tier_line}"
        f"<li>Monthly cost: <strong>{monthly_cost_display}</strong></li>"
        f"</ul>"
        f"<p><a href=\"{checkout_url}\">Set up your subscription and pay securely through Stripe</a>.</p>"
        f"<p style=\"color:#888;font-size:13px\">If the button doesn't work, paste this into "
        f"your browser:<br>{checkout_url}</p>"
    )
    send_email(to, subject, html)
    return subject


def send_billing_payment_issue_email(to: str, studio_name: str, status: str) -> str:
    """Notify a studio's contact when their platform subscription (Stripe
    Studio Billing) hits a payment problem or lapses — "if they have a
    payment issue then it turns red and the studio is notified". `status` is
    `'past_due'` or `'canceled'` — the only two states the billing webhook
    triggers this for. Returns the subject line, same convention as the
    other send_* functions here."""
    if status == "canceled":
        subject = f"Your Mickeymouse House subscription has been canceled — {studio_name}"
        body_line = "Your subscription has been canceled, and billing is no longer active for your studio."
    else:
        subject = f"Payment problem with your Mickeymouse House subscription — {studio_name}"
        body_line = "We were unable to process your latest subscription payment."
    html = (
        f"<p>Hi there,</p>"
        f"<p>{body_line}</p>"
        f"<p>Please sign in to Mickeymouse House and open the <strong>Billing</strong> tab "
        f"to fix this and keep your studio's subscription active.</p>"
    )
    send_email(to, subject, html)
    return subject


def send_pricing_tier_changed_email(
    to: str, studio_name: str, old_tier_name: str, new_tier_name: str, new_price_display: str,
) -> str:
    """Notify a studio's contact when its pricing-tier LABEL changes — manual
    assignment only, triggered from `PUT /api/studios/{id}` when
    `pricing_tier_id` actually changes. Returns the subject line (handy in
    dev/test visibility, same convention as the other send_* functions here
    returning something useful rather than None).

    Deliberately says this does NOT change the studio's actual bill — same
    tone as the pricing-tiers admin page itself ("Editing here does not
    change any studio's actual bill; see Billing for that."). The real,
    hand-set billing amount lives on StudioSubscription.contracted_amount_cents
    and is untouched by this email or the field that triggers it.
    """
    subject = f"Your Mickeymouse House pricing tier has changed — {studio_name}"
    html = (
        f"<p>Hi there,</p>"
        f"<p><strong>{studio_name}</strong>'s pricing tier has been updated:</p>"
        f"<ul>"
        f"<li>Previous tier: <strong>{old_tier_name}</strong></li>"
        f"<li>New tier: <strong>{new_tier_name}</strong></li>"
        f"<li>New tier's monthly price: <strong>{new_price_display}</strong></li>"
        f"</ul>"
        f"<p style=\"color:#888;font-size:13px\">This is an internal label change only "
        f"— it does not change any studio's actual bill or what you've already been "
        f"charged for past periods. If you have questions about your actual billing, "
        f"please reach out to us directly.</p>"
    )
    send_email(to, subject, html)
    return subject


def send_invite_email(to: str, name: str, token: str,
                      intro: str = "You've been invited to Mickeymouse House.") -> str:
    """Send the set-password magic link. Returns the link (handy in dev)."""
    link = invite_link(token)
    subject = "Set up your Mickeymouse House account"
    html = (
        f"<p>Hi {name or 'there'},</p>"
        f"<p>{intro}</p>"
        f"<p><a href=\"{link}\">Set your password</a> to finish.</p>"
        f"<p style=\"color:#888;font-size:13px\">This link expires in 72 hours. "
        f"If the button doesn't work, paste this into your browser:<br>{link}</p>"
    )
    send_email(to, subject, html)
    return link
