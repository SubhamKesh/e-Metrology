"""
Status-update emails for owners (the business people who register machines).

Owners get an email for every step of an instrument's life:

  instrument_registered   -> machine registered, UIID issued
  application_submitted   -> verification application received
  application_scheduled   -> an officer claimed it, inspection scheduled
  inspection_passed       -> inspection passed (certificate being generated)
  inspection_failed       -> inspection failed, application rejected
  certificate_issued      -> certificate ready (PDF + verify link)
  expiry_reminder         -> 30 / 15 / 7 / 1 days before expiry (settings)
  certificate_expired     -> certificate has expired

Design rules
  * Never break the caller. Every public notify_*() swallows and logs its own
    errors: a mail problem must not fail an inspection or a registration.
  * Never block the caller. Mail goes out via the RQ queue when REDIS_URL is
    set (with retries), otherwise via a short-lived daemon thread. The expiry
    cron sends inline because it already runs in a background thread.
  * Never send the same mail twice. Each mail has a dedupe key which is
    claimed atomically in the `email_log` collection (key = _id) before the
    SMTP send. A failed send releases the claim so a retry can succeed.
  * No SMTP configured -> silent no-op (checked before any DB work).
"""
from __future__ import annotations

import functools
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.config.db import email_log_col, users_col
from app.config.settings import (
    EXPIRY_REMINDER_DAYS,
    FRONTEND_BASE_URL,
    FRONTEND_VERIFY_URL,
    OWNER_EMAIL_NOTIFICATIONS_ENABLED,
)
from app.services import mailer
from app.services.email_templates import render
from app.utils.location_format import format_location

logger = logging.getLogger("maapsetu")

# Route owner emails through the RQ queue only if explicitly enabled. The queue
# needs a separate worker process (run_worker.py); on hosts without one (e.g.
# Render free tier) jobs would sit in Redis forever and no email would go out.
# Default: send from a short-lived daemon thread inside the web process.
EMAIL_USE_QUEUE = os.getenv("EMAIL_USE_QUEUE", "false").strip().lower() == "true"

# A claim stuck in "sending" longer than this belonged to a crashed process
# and may be taken over.
_STALE_CLAIM_MINUTES = 10


class EmailDeliveryError(Exception):
    """Raised by the send job so RQ can retry it."""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

_warned_disabled = False


def _enabled() -> bool:
    """True if owner status emails should be attempted. When not, log the
    reason once per process -- this used to return False silently, which made
    "no status emails are arriving" impossible to diagnose from the logs."""
    global _warned_disabled
    if OWNER_EMAIL_NOTIFICATIONS_ENABLED and mailer.is_configured():
        return True
    if not _warned_disabled:
        _warned_disabled = True
        logger.warning(
            "Owner status emails are DISABLED: OWNER_EMAIL_NOTIFICATIONS_ENABLED=%s, mailer configured=%s "
            "(needs BREVO_API_KEY + SMTP_FROM, or SMTP_HOST + SMTP_FROM).",
            OWNER_EMAIL_NOTIFICATIONS_ENABLED, mailer.is_configured(),
        )
    return False


def _never_raises(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("Owner notification %s failed (ignored)", fn.__name__)
            return None

    return wrapper


def _as_utc(dt):
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # Mongo returns naive UTC
    return dt


def _to_oid(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return value


def _get_owner(owner_id) -> Optional[dict]:
    owner = users_col.find_one({"_id": _to_oid(owner_id)})
    if owner is None and owner_id is not None:
        owner = users_col.find_one({"_id": owner_id})
    return owner


def _instrument_ctx(instrument: dict) -> dict:
    try:
        location = format_location(instrument.get("location"))
    except Exception:
        location = None
    return {
        "type": instrument.get("type"),
        "uiid": instrument.get("uiid"),
        "manufacturer": instrument.get("manufacturer"),
        "model": instrument.get("model"),
        "serial_no": instrument.get("serial_no"),
        "location": location,
    }


def _application_url(application_id) -> str:
    return f"{FRONTEND_BASE_URL}/app/owner/applications/{application_id}"


def _renew_url(instrument_id) -> str:
    return f"{FRONTEND_BASE_URL}/app/owner/applications/new?instrument={instrument_id}"


# --------------------------------------------------------------------------
# Sending: claim -> SMTP -> confirm/release
# --------------------------------------------------------------------------

def send_owner_email_job(dedupe_key: str, to: str, subject: str, text: str, html: str) -> bool:
    """Runs in an RQ worker, a daemon thread, or inline (cron).

    Returns True if sent, False if this dedupe_key was already sent (or is
    being sent right now). Raises EmailDeliveryError if SMTP failed, after
    releasing the claim, so RQ retries and the next cron tick can retry.
    """
    now = datetime.now(timezone.utc)
    try:
        email_log_col.insert_one(
            {"_id": dedupe_key, "to": to, "subject": subject, "status": "sending", "created_at": now}
        )
    except DuplicateKeyError:
        # Take over only a stale claim from a crashed process; anything else
        # means it was already sent or is in flight.
        taken = email_log_col.update_one(
            {
                "_id": dedupe_key,
                "status": "sending",
                "created_at": {"$lt": now - timedelta(minutes=_STALE_CLAIM_MINUTES)},
            },
            {"$set": {"created_at": now}},
        )
        if taken.matched_count == 0:
            logger.info("Owner email %s already sent/in flight; skipping.", dedupe_key)
            return False

    ok = mailer.send_email(to, subject, text, html=html)
    if not ok:
        email_log_col.delete_one({"_id": dedupe_key, "status": "sending"})
        logger.error("Owner email %s to %s was NOT delivered (see the mailer log line above for the cause).", dedupe_key, to)
        raise EmailDeliveryError(f"SMTP send failed for {dedupe_key}")

    email_log_col.update_one(
        {"_id": dedupe_key}, {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc)}}
    )
    logger.info("Owner email %s sent to %s.", dedupe_key, to)
    return True


def _run_quietly(*args) -> None:
    try:
        send_owner_email_job(*args)
    except EmailDeliveryError:
        logger.warning("Owner email %s could not be delivered.", args[0])
    except Exception:
        logger.exception("Owner email %s failed unexpectedly.", args[0])


def _get_queue():
    # Imported lazily: jobs.py imports cert_generator, which imports this
    # module -- a top-level import here would be circular.
    from app.services.jobs import get_queue

    return get_queue()


# Seconds to wait before retry #1, #2, #3 of a failed owner email. An immediate
# retry (the old behaviour) burns all attempts inside a short SMTP outage; this
# spreads them over ~6 minutes. RQ's Retry takes the number of retries from the
# length of the interval list.
EMAIL_RETRY_INTERVALS = [10, 60, 300]


def _dispatch(dedupe_key, to, subject, text, html, *, inline: bool = False) -> None:
    args = (dedupe_key, to, subject, text, html)
    if inline:
        _run_quietly(*args)
        return
    queue = _get_queue() if EMAIL_USE_QUEUE else None
    if queue is not None:
        try:
            from rq import Retry, Worker

            # A web-only deploy (e.g. a single Render web service) has no
            # process running run_worker.py. Enqueueing then "succeeds" and the
            # job sits in Redis forever -- no email, no error. Only use the
            # queue if a worker is actually registered on it.
            if Worker.count(queue=queue) > 0:
                queue.enqueue(
                    send_owner_email_job,
                    *args,
                    retry=Retry(max=len(EMAIL_RETRY_INTERVALS), interval=EMAIL_RETRY_INTERVALS),
                )
                logger.info("Owner email %s queued for %s.", dedupe_key, to)
                return
            logger.warning(
                "EMAIL_USE_QUEUE=true but no RQ worker is listening; sending %s in a thread instead.", dedupe_key
            )
        except Exception:
            logger.warning("Could not enqueue owner email %s; sending in a thread.", dedupe_key, exc_info=True)
    logger.info("Owner email %s sending in background thread to %s.", dedupe_key, to)
    threading.Thread(target=_run_quietly, args=args, daemon=True).start()


def _send(event: str, dedupe_key: str, owner_id, instrument: dict, extra: dict, *, inline: bool = False) -> None:
    if not _enabled():
        return
    owner = _get_owner(owner_id)
    if not owner or not owner.get("email"):
        logger.warning("Owner %s has no email on file; skipping %s.", owner_id, event)
        return
    ctx = {
        "owner_name": owner.get("name") or "there",
        "instrument": _instrument_ctx(instrument),
        **extra,
    }
    subject, text, html = render(event, ctx)
    _dispatch(dedupe_key, owner["email"], subject, text, html, inline=inline)


def _load_instrument(instrument_id) -> Optional[dict]:
    from app.config.db import instruments_col

    return instruments_col.find_one({"_id": instrument_id})


# --------------------------------------------------------------------------
# Public API -- one function per event
# --------------------------------------------------------------------------

@_never_raises
def notify_instrument_registered(instrument: dict) -> None:
    """instrument: the stored instrument doc (with _id)."""
    if not _enabled():
        return
    iid = instrument["_id"]
    _send(
        "instrument_registered",
        f"instrument_registered:{iid}",
        instrument["owner_id"],
        instrument,
        {"apply_url": f"{FRONTEND_BASE_URL}/app/owner/applications/new?instrument={iid}"},
    )


@_never_raises
def notify_application_submitted(application: dict) -> None:
    if not _enabled():
        return
    instrument = _load_instrument(application["instrument_id"])
    if not instrument:
        return
    app_id = application["_id"]
    _send(
        "application_submitted",
        f"application_submitted:{app_id}",
        application["owner_id"],
        instrument,
        {"application_id": str(app_id), "application_url": _application_url(app_id)},
    )


@_never_raises
def notify_application_scheduled(application: dict) -> None:
    if not _enabled():
        return
    instrument = _load_instrument(application["instrument_id"])
    if not instrument:
        return
    app_id = application["_id"]
    _send(
        "application_scheduled",
        f"application_scheduled:{app_id}",
        application["owner_id"],
        instrument,
        {"application_id": str(app_id), "application_url": _application_url(app_id)},
    )


@_never_raises
def notify_inspection_result(application: dict, inspection: dict) -> None:
    """Call after the inspection is stored and the application has moved to
    certified (pass) or rejected (fail)."""
    if not _enabled():
        return
    instrument = _load_instrument(application["instrument_id"])
    if not instrument:
        return
    app_id = application["_id"]
    passed = inspection.get("result") == "pass"
    event = "inspection_passed" if passed else "inspection_failed"
    _send(
        event,
        f"{event}:{app_id}",
        application["owner_id"],
        instrument,
        {
            "application_id": str(app_id),
            "application_url": _application_url(app_id),
            "reapply_url": _renew_url(instrument["_id"]),
            "inspected_at": inspection.get("inspected_at"),
            "observations": inspection.get("observations"),
        },
    )


@_never_raises
def notify_certificate_issued(cert: dict) -> None:
    """cert: the stored certificate doc."""
    if not _enabled():
        return
    instrument = _load_instrument(cert["instrument_id"])
    if not instrument:
        return
    _send(
        "certificate_issued",
        f"certificate_issued:{cert['_id']}",
        instrument["owner_id"],
        instrument,
        {
            "cert_no": cert["cert_no"],
            "issued_at": cert.get("issued_at"),
            "valid_until": cert.get("valid_until"),
            "pdf_url": cert.get("pdf_url"),
            "certificate_url": f"{FRONTEND_BASE_URL}/app/owner/certificates/{cert['_id']}",
            "verify_url": f"{FRONTEND_VERIFY_URL.rstrip('/')}/{cert['_id']}",
        },
    )


def pick_reminder_milestone(days_left: int) -> Optional[int]:
    """Smallest configured milestone that days_left has reached, e.g. with
    (30, 15, 7, 1): 20 days left -> 30, 5 -> 7, 0 -> 1, 45 -> None. Sending
    only the tightest milestone means a server that was down for a week
    doesn't fire three stale reminders at once."""
    due = [m for m in EXPIRY_REMINDER_DAYS if days_left <= m]
    return min(due) if due else None


@_never_raises
def notify_expiry_reminder(cert: dict, *, now: Optional[datetime] = None, inline: bool = True) -> None:
    if not _enabled():
        return
    now = now or datetime.now(timezone.utc)
    valid_until = _as_utc(cert["valid_until"])
    days_left = max(0, math.ceil((valid_until - now).total_seconds() / 86400))
    milestone = pick_reminder_milestone(days_left)
    if milestone is None:
        return
    instrument = _load_instrument(cert["instrument_id"])
    if not instrument:
        return
    _send(
        "expiry_reminder",
        f"expiry_reminder:{cert['_id']}:{milestone}",
        instrument["owner_id"],
        instrument,
        {
            "cert_no": cert["cert_no"],
            "valid_until": valid_until,
            "days_left": days_left,
            "renew_url": _renew_url(instrument["_id"]),
        },
        inline=inline,
    )


@_never_raises
def notify_certificate_expired(cert: dict, *, inline: bool = True) -> None:
    if not _enabled():
        return
    instrument = _load_instrument(cert["instrument_id"])
    if not instrument:
        return
    _send(
        "certificate_expired",
        f"certificate_expired:{cert['_id']}",
        instrument["owner_id"],
        instrument,
        {
            "cert_no": cert["cert_no"],
            "valid_until": _as_utc(cert["valid_until"]),
            "renew_url": _renew_url(instrument["_id"]),
        },
        inline=inline,
    )
