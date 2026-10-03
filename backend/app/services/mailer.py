"""Minimal SMTP mailer. Uses only smtplib/email from the stdlib — no new
dependency — so it works the moment SMTP_* env vars are set, and simply
logs instead of failing when they aren't (e.g. local dev).
"""

import json
import logging
import smtplib
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr

from app.config.settings import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
    SMTP_USE_TLS,
    BREVO_API_KEY,
    FRONTEND_LOGIN_URL,
)

logger = logging.getLogger("app.mailer")


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _brevo_configured() -> bool:
    return bool(BREVO_API_KEY and SMTP_FROM)


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def _send_via_brevo(to: str, subject: str, body: str, html: str | None) -> bool:
    """Send through Brevo's HTTP API (HTTPS/443) -- works on hosts that block
    outbound SMTP ports. SMTP_FROM must be a sender verified in Brevo; it may
    be a bare address or 'Name <address>'."""
    sender_name, sender_email = parseaddr(SMTP_FROM)
    sender = {"email": sender_email or SMTP_FROM}
    if sender_name:
        sender["name"] = sender_name
    payload = {
        "sender": sender,
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    if html:
        payload["htmlContent"] = html
    req = urllib.request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": BREVO_API_KEY,
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok = 200 <= resp.status < 300
            logger.info("Brevo accepted email to %s (status %s): %s", to, resp.status, subject)
            return ok
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        logger.error("Brevo API rejected email to %s: %s %s", to, e.code, detail)
        return False
    except Exception:  # pragma: no cover - network failure
        logger.exception("Brevo API request failed for %s", to)
        return False


def is_configured() -> bool:
    """Just an env-var check, no network -- safe to call synchronously
    from a request even after send_email() itself moves to a background
    job (see routers/admin_users.py), to tell an admin up front whether an
    email will be attempted at all, versus them needing to share the temp
    password some other way."""
    return _brevo_configured() or _smtp_configured()


def send_email(to: str, subject: str, body: str, html: str | None = None) -> bool:
    """Best-effort send. Returns True if actually sent, False if SMTP isn't
    configured or the send failed — callers should never let a False here
    block the calling request, since the account creation itself already
    succeeded by the time this runs."""
    if _brevo_configured():
        return _send_via_brevo(to, subject, body, html)

    if not _smtp_configured():
        logger.warning("Email not configured; skipping email to %s (subject: %s)", to, subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(body)
    if html:
        # Plain text stays as the fallback part; clients that render HTML show this.
        msg.add_alternative(html, subtype="html")

    # 30s, not the original 10s -- this now runs in a background worker
    # (see app/services/jobs.py), not inline in a request, so a slower
    # ceiling here costs nothing user-facing. Some mail relays (and some
    # antivirus software's SMTP-scanning proxies on the client side) are
    # simply slower than 10s to hand back a final reply after the message
    # body is sent, without anything actually being broken.
    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception:  # pragma: no cover - network/credentials failure
        logger.exception("Failed to send email to %s", to)
        return False


def send_officer_credentials(*, to: str, name: str, role: str, temp_password: str) -> bool:
    role_label = "Legal Metrology Officer" if role == "lmo" else "GATC"
    subject = "Your MaapSetu account has been created"
    body = (
        f"Hello {name},\n\n"
        f"An administrator has created a {role_label} account for you on MaapSetu.\n\n"
        f"Email: {to}\n"
        f"Temporary password: {temp_password}\n\n"
        f"Sign in here: {FRONTEND_LOGIN_URL}\n\n"
        "You will be asked to set your own password the first time you sign in. "
        "This temporary password will stop working once you do.\n\n"
        "If you weren't expecting this account, please contact your department administrator.\n"
    )
    return send_email(to, subject, body)


def send_admin_password_reset(*, to: str, name: str, temp_password: str) -> bool:
    """Sent when an administrator resets an officer's password for them."""
    body = (
        f"Hello {name},\n\n"
        "An administrator has reset the password for your MaapSetu account.\n\n"
        f"Email: {to}\n"
        f"Temporary password: {temp_password}\n\n"
        f"Sign in here: {FRONTEND_LOGIN_URL}\n\n"
        "You will be asked to set your own password the first time you sign in. "
        "This temporary password will stop working once you do, and you have been "
        "signed out of all other sessions.\n\n"
        "If you did not expect this, contact your department administrator immediately.\n"
    )
    return send_email(to, "Your MaapSetu password was reset by an administrator", body)


def send_password_changed_notice(*, to: str, name: str) -> bool:
    """Security alert after a password change/reset, so the real owner finds
    out quickly if someone else did it. Never contains the password."""
    ist = timezone(timedelta(hours=5, minutes=30))
    when = datetime.now(ist).strftime("%d %b %Y, %H:%M IST")
    body = (
        f"Hello {name},\n\n"
        f"The password for your MaapSetu account ({to}) was changed on {when}.\n\n"
        "If this was you, no action is needed.\n\n"
        "If this was NOT you, someone else may have access to your account or email. "
        "Reset your password again right away and contact your department administrator.\n"
    )
    return send_email(to, "Your MaapSetu password was changed", body)
