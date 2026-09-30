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

from app.config.settings import REDIS_URL
from app.config.db import applications_col
from app.services.cert_generator import issue_certificate
from app.services.notifications import publish_notification_sync
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


def generate_certificate_job(inspection_id: str) -> None:
    """The job a worker process (run_worker.py) actually executes -- not
    called directly by any router. Routers enqueue this by reference via
    get_queue().enqueue(generate_certificate_job, ...) instead, so it runs
    in the separate worker process, not the web process handling the
    original request.

    Any exception here is left to propagate -- RQ records the job as
    failed (visible via RQ's FailedJobRegistry) rather than silently
    losing it, which is the right behaviour for something that isn't in a
    request/response cycle any more and so has no HTTP response to carry
    an error back on.
    """
    cert_doc = issue_certificate(inspection_id)

    application = applications_col.find_one({"_id": cert_doc["application_id"]})
    if not application:
        # Certificate exists; just can't figure out who to notify. Log
        # and move on -- the owner still sees the certificate next time
        # they load the app, this only affects the real-time push.
        logger.warning(
            "Certificate %s issued but its application %s is gone; skipping notification.",
            cert_doc["_id"], cert_doc["application_id"],
        )
        return

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
    # -- owner, jurisdiction, and (new here) the specific officer who
    # handled it, so they get notified even if they're outside their own
    # jurisdiction's usual filter for some reason.
    audience = {
        "owner_id": str(application["owner_id"]),
        "officer_id": str(application["assigned_officer_id"]) if application.get("assigned_officer_id") else None,
        "state_code": application.get("state_code"),
        "district_code": application.get("district_code"),
    }
    publish_notification_sync(payload, audience)


def send_officer_credentials_job(to: str, name: str, role: str, temp_password: str) -> None:
    """The job a worker process executes for a newly-created officer
    account's welcome email. Fire-and-forget from the router's point of
    view (see routers/admin_users.py) -- nothing waits on this finishing,
    and nothing needs to, since the account itself already exists by the
    time this runs; only the email is delayed, not the account creation.
    """
    send_officer_credentials(to=to, name=name, role=role, temp_password=temp_password)
