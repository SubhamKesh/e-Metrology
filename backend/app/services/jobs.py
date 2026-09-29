"""
Background job queue for certificate generation (PDF render, QR code,
Cloudinary upload) -- moves that work out of the request path.

issue_certificate() (cert_generator.py) does real, slow work: a CPU-bound
PDF render, a QR-code image generation, and two Cloudinary uploads. Doing
that inline, as routers/inspections.py used to, ties up a threadpool
worker thread for however long Cloudinary/reportlab take -- fine at
hackathon traffic, a real bottleneck at production volume, exactly the
kind of thing flagged early in the scalability review.

With REDIS_URL set, routers/inspections.py enqueues generate_certificate_job
instead of calling issue_certificate directly, and returns immediately; a
separate worker process (run_worker.py, its own terminal/process, same
idea as running a second uvicorn instance) picks the job up and runs it.
Without REDIS_URL, get_queue() returns None -- there's no queue to enqueue
onto, so the router falls back to calling issue_certificate() inline,
exactly as before this existed. Same graceful-degradation shape as every
other Redis-dependent piece in this project.

The client finds out the certificate is ready via the same audience-scoped
WebSocket notifications built in services/notifications.py -- a
"certificate_ready" event reaches the owner and any assigned officer, the
same way "application_submitted" already does.
"""
import logging

from app.config.settings import REDIS_URL
from app.config.db import applications_col
from app.services.cert_generator import issue_certificate
from app.services.notifications import publish_notification_sync

logger = logging.getLogger("maapsetu")

QUEUE_NAME = "certificates"

# Lazily created -- both `rq` and a live Redis connection are only needed
# when REDIS_URL is actually set, so importing this module doesn't require
# either in an environment that never configures Redis at all.
_queue = None


def get_queue():
    """None if REDIS_URL isn't set -- routers/inspections.py checks this
    and falls back to calling issue_certificate() directly in that case."""
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
