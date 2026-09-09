"""Minimal SMTP mailer. Uses only smtplib/email from the stdlib — no new
dependency — so it works the moment SMTP_* env vars are set, and simply
logs instead of failing when they aren't (e.g. local dev).
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config.settings import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
    SMTP_USE_TLS,
    FRONTEND_LOGIN_URL,
)

logger = logging.getLogger("app.mailer")


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def send_email(to: str, subject: str, body: str) -> bool:
    """Best-effort send. Returns True if actually sent, False if SMTP isn't
    configured or the send failed — callers should never let a False here
    block the calling request, since the account creation itself already
    succeeded by the time this runs."""
    if not _smtp_configured():
        logger.warning("SMTP not configured; skipping email to %s (subject: %s)", to, subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(body)

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
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
