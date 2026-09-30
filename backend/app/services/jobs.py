"""
Background job queue -- moves slow, non-critical-path work out of the
request/response cycle.

Two kinds of job live here so far:

  - generate_certificate_job: PDF render, QR-code image, two Cloudinary
    uploads. CPU- and I/O-heavy; used to run inline in
    routers/inspections.py, tying up a threadpool worker thread for
    however long that took.
  - send_officer_credentials_job: one SMTP send. Used to run inline in
    routers/admin_users.py, blocking the officer-creation response on
    however long the mail server took to answer.

Both share one queue (QUEUE_NAME = "default") and one worker process
(run_worker.py) -- there's no need for a job-type-specific queue at this
project's scale, and one worker can run a mix of job types from a single
queue without any special handling.

With REDIS_URL set, a router enqueues the job and returns immediately; the
separate worker process (its own terminal, same idea as running a second
uvicorn instance) picks it up and runs it. Without REDIS_URL, get_queue()
returns None -- there's no queue to enqueue onto, so each call site falls
back to running the equivalent work inline, exactly as it did before this
module existed. Same graceful-degradation shape as every other
Redis-dependent piece in this project.

Certificate readiness reaches the client via the same audience-scoped
WebSocket notifications built in services/notifications.py -- a
"certificate_ready" event reaches the owner and any assigned officer, the
same way "application_submitted" already does. The email job has no
real-time notification counterpart -- there's nothing to push, since the
officer-creation response already returned before the email is actually
sent (see routers/admin_users.py for how it reports this to the admin).
"""
import logging
import threading
import time

from app.config.settings import REDIS_URL
from app.config.db import applications_col
from app.services.cert_generator import issue_certificate
from app.services.notifications import publish_notification_sync, broadcast_threadsafe
from app.services.mailer import send_officer_credentials

logger = logging.getLogger("maapsetu")

QUEUE_NAME = "default"

# Lazily created -- both `rq` and a live Redis connection are only needed
# when REDIS_URL is actually set, so importing this module doesn't require
# either in an environment that never configures Redis at all.
_queue = None


def get_queue():
    """None if REDIS_URL isn't set -- callers check this and fall back to
    running the equivalent work inline in that case."""
    global _queue
    if _queue is None and REDIS_URL:
        from redis import Redis
        from rq import Queue

        _queue = Queue(QUEUE_NAME, connection=Redis.from_url(REDIS_URL))
    return _queue


def _certificate_ready_message(cert_doc: dict):
    """(payload, audience) for the "certificate_ready" WebSocket event, or
    None if the certificate's application can't be found."""
    application = applications_col.find_one({"_id": cert_doc["application_id"]})
    if not application:
        # Certificate exists; just can't figure out who to notify. Log
        # and move on -- the owner still sees the certificate next time
        # they load the app, this only affects the real-time push.
        logger.warning(
            "Certificate %s issued but its application %s is gone; skipping notification.",
            cert_doc["_id"], cert_doc["application_id"],
        )
        return None

    payload = {
        "type": "certificate_ready",
        "certificate": {
            "id": cert_doc["_id"],
            "cert_no": cert_doc["cert_no"],
            "application_id": str(cert_doc["application_id"]),
            "pdf_url": cert_doc["pdf_url"],
        },
    }
    # Same audience shape as "application_submitted" (routers/applications.py)
    # -- owner, jurisdiction, and the specific officer who handled it.
    audience = {
        "owner_id": str(application["owner_id"]),
        "officer_id": str(application["assigned_officer_id"]) if application.get("assigned_officer_id") else None,
        "state_code": application.get("state_code"),
        "district_code": application.get("district_code"),
    }
    return payload, audience


def generate_certificate_job(inspection_id: str) -> None:
    """The job a worker process (run_worker.py) executes -- enqueued by
    start_certificate_generation() below, not called directly by routers.

    Any exception here is left to propagate -- RQ records the job as
    failed (visible via RQ's FailedJobRegistry) rather than silently
    losing it, since there is no HTTP response left to carry an error.
    """
    cert_doc = issue_certificate(inspection_id)
    message = _certificate_ready_message(cert_doc)
    if message:
        publish_notification_sync(*message)


# Backoff between attempts when generating in a thread (Cloudinary / the QR
# fetch can fail transiently). Three tries in total.
_INLINE_RETRY_DELAYS = (5, 20)


def _generate_certificate_in_thread(inspection_id: str) -> None:
    attempts = len(_INLINE_RETRY_DELAYS) + 1
    for attempt in range(1, attempts + 1):
        try:
            cert_doc = issue_certificate(inspection_id)
            logger.info("Certificate %s issued for inspection %s.", cert_doc["_id"], inspection_id)
            message = _certificate_ready_message(cert_doc)
            if message:
                # Works with or without Redis, and from a non-event-loop thread.
                broadcast_threadsafe(*message)
            return
        except Exception:
            logger.exception(
                "Certificate generation failed for inspection %s (attempt %d/%d).",
                inspection_id, attempt, attempts,
            )
            if attempt < attempts:
                time.sleep(_INLINE_RETRY_DELAYS[attempt - 1])
    logger.error(
        "Giving up on certificate generation for inspection %s. The application is still 'certified'; "
        "re-issue it with POST /api/v1/certificates/generate/<application_id>.",
        inspection_id,
    )


def _worker_available(queue) -> bool:
    """True only if a worker process is actually registered on this queue.
    With REDIS_URL set but no worker (e.g. a single Render web service),
    enqueueing "succeeds" and the job then sits in Redis forever -- which is
    exactly how certificates silently never got generated."""
    try:
        from rq import Worker

        return Worker.count(queue=queue) > 0
    except Exception:
        logger.warning("Could not check for RQ workers.", exc_info=True)
        return False


def start_certificate_generation(inspection_id: str) -> None:
    """Kick off certificate generation for a passed inspection without
    blocking the request. Uses the RQ worker when one is running, otherwise a
    background thread in this process (with retries). Never raises."""
    inspection_id = str(inspection_id)
    try:
        queue = get_queue()
        if queue is not None and _worker_available(queue):
            queue.enqueue(generate_certificate_job, inspection_id)
            logger.info("Certificate generation for inspection %s queued for the RQ worker.", inspection_id)
            return
        if queue is not None:
            logger.warning(
                "REDIS_URL is set but no RQ worker is running; generating the certificate for inspection %s "
                "in a background thread instead.", inspection_id,
            )
    except Exception:
        logger.warning("Could not enqueue certificate generation for %s; using a thread.", inspection_id, exc_info=True)
    threading.Thread(target=_generate_certificate_in_thread, args=(inspection_id,), daemon=True).start()


def send_officer_credentials_job(to: str, name: str, role: str, temp_password: str) -> None:
    """The job a worker process executes for a newly-created officer
    account's welcome email. Fire-and-forget from the router's point of
    view (see routers/admin_users.py) -- nothing waits on this finishing,
    and nothing needs to, since the account itself already exists by the
    time this runs; only the email is delayed, not the account creation.
    """
    send_officer_credentials(to=to, name=name, role=role, temp_password=temp_password)
