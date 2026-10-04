"""Append-only security audit trail.

Records who did what, to which account, from where, and whether it worked —
for the password flows (reset requested / completed / failed, password
changed, administrator-initiated reset). Every event is written twice:

  1. as one structured line on the `app.audit` logger (stdout, so it shows
     up in Render's log stream and can be shipped to a log service), and
  2. as a document in the `audit_logs` collection (retained for
     AUDIT_LOG_RETENTION_DAYS, see config/db.py).

Auditing is best-effort by design: a failure to write the log must never
turn a legitimate password reset into a 500, so errors are caught and
logged instead of raised. Never put secrets (passwords, reset codes,
tokens) in `detail`.
"""

import logging
from datetime import datetime, timezone

from fastapi import Request

from app.config.db import audit_logs_col

logger = logging.getLogger("app.audit")

AUDIT_OUTCOMES = ("success", "failure", "blocked", "ignored")

# Every event name the application writes — used by the admin audit-log viewer
# for its filter. tests/test_audit_viewer.py parses the source and fails if a
# log_event("...") call uses a name that isn't listed here (or one listed here
# is never used), so this can't silently drift.
KNOWN_AUDIT_EVENTS = (
    "login_success",
    "login_failed",
    "login_blocked",
    "login_password_verified",
    "mfa_setup_started",
    "mfa_enabled",
    "mfa_failed",
    "mfa_blocked",
    "mfa_reset",
    "logout",
    "logout_all",
    "refresh_rejected",
    "account_registered",
    "account_registration_failed",
    "signup_otp_requested",
    "officer_created",
    "officer_creation_failed",
    "account_approved",
    "account_suspended",
    "password_reset_requested",
    "password_reset_completed",
    "password_reset_failed",
    "password_changed",
    "password_change_failed",
    "admin_password_reset",
)


def client_ip(request: Request | None) -> str | None:
    """Same rule as the DDoS middleware: first X-Forwarded-For hop when
    behind a proxy (Render), otherwise the socket peer."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def log_event(
    event: str,
    *,
    outcome: str,
    request: Request | None = None,
    email: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
    actor_id: str | None = None,
    actor_email: str | None = None,
    detail: str | None = None,
) -> None:
    """event:   e.g. "password_reset_requested"
    outcome:    "success" | "failure" | "blocked" | "ignored"
    email/user_id/role: the account the event is about (if one was identified)
    actor_id:   who performed it when it isn't the account itself (admin reset)
    actor_email: that actor's email, stored with the record so the history stays
                readable even if the actor's account is later changed or removed
    detail:     short machine-readable reason, e.g. "invalid_or_expired_code"
    """
    record = {
        "event": event,
        "outcome": outcome,
        "email": email,
        "user_id": user_id,
        "role": role,
        "actor_id": actor_id,
        "actor_email": actor_email,
        "ip": client_ip(request),
        "user_agent": ((request.headers.get("user-agent") or "")[:200] or None) if request else None,
        "detail": detail,
        "created_at": datetime.now(timezone.utc),
    }
    logger.info(
        "AUDIT event=%s outcome=%s email=%s role=%s actor=%s ip=%s detail=%s",
        event, outcome, email, role, actor_id, record["ip"], detail,
    )
    try:
        audit_logs_col.insert_one(record)
    except Exception:
        logger.exception("Failed to persist audit record for event=%s", event)
