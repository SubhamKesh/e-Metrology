import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta

from app.config.db import certificates_col, alerts_col
from app.config.settings import REDIS_URL
from app.services.status_transition import mark_expiring, mark_expired, InvalidTransitionError, ApplicationNotFoundError

logger = logging.getLogger("maapsetu")

# How long a job's run-lock is held, in seconds. Generous relative to how
# long a scan-and-update over certificates actually takes, so a crashed
# instance's stale lock never blocks other instances for long — the next
# scheduled tick an hour later succeeds regardless, and a shorter gap in
# between is fine to just skip.
_LOCK_TTL_SECONDS = 600  # 10 minutes

# A plain *synchronous* Redis client — deliberately not redis.asyncio like
# middleware/ddos_store.py and services/notifications.py use. APScheduler's
# BackgroundScheduler runs jobs in ordinary background threads, not inside
# the asyncio event loop, so there's no running loop here to await against.
_redis = None


def _get_redis():
    global _redis
    if _redis is None and REDIS_URL:
        import redis as redis_sync

        _redis = redis_sync.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _acquire_run_lock(job_name: str) -> bool:
    """True if this instance should actually run the job this tick.

    With REDIS_URL set, only one instance across the whole fleet acquires
    the lock per tick — `SET ... NX` is atomic ("set only if not already
    set"), so every other instance's scheduler just sees the key already
    exists and skips this tick entirely, without doing any of the
    certificate-scan work.

    Without Redis, always returns True — the original single-instance
    behaviour, since there's no other instance to coordinate with anyway.
    """
    redis = _get_redis()
    if redis is None:
        return True
    acquired = bool(redis.set(f"scheduler-lock:{job_name}", "1", nx=True, ex=_LOCK_TTL_SECONDS))
    if not acquired:
        logger.info("Skipping %s this tick — another instance already holds the run-lock.", job_name)
    return acquired


def check_expiring_certificates():
    """Certificates within 30 days of expiry: send a reminder (once) and
    move their application to 'expiring' if it's still 'certified'."""
    if not _acquire_run_lock("check_expiring_certificates"):
        return

    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=30)

    expiring = certificates_col.find({
        "valid_until": {"$lte": soon, "$gte": now}
    })

    for cert in expiring:
        exists = alerts_col.find_one({
            "certificate_id": cert["_id"],
            "alert_type": "expiry_reminder",
        })
        if not exists:
            alerts_col.insert_one({
                "certificate_id": cert["_id"],
                "alert_type": "expiry_reminder",
                "sent_at": now,
            })

        try:
            mark_expiring(cert["application_id"])
        except (InvalidTransitionError, ApplicationNotFoundError):
            # Already past 'certified' (e.g. already 'expiring'), or the
            # application vanished — either way, nothing to do here.
            pass


def check_expired_certificates():
    """Certificates whose valid_until has passed: move application to
    'expired' if it's currently 'expiring', and log an expired alert."""
    if not _acquire_run_lock("check_expired_certificates"):
        return

    now = datetime.now(timezone.utc)
    expired = certificates_col.find({"valid_until": {"$lt": now}})

    for cert in expired:
        exists = alerts_col.find_one({
            "certificate_id": cert["_id"],
            "alert_type": "expired",
        })
        if not exists:
            alerts_col.insert_one({
                "certificate_id": cert["_id"],
                "alert_type": "expired",
                "sent_at": now,
            })

        try:
            mark_expired(cert["application_id"])
        except (InvalidTransitionError, ApplicationNotFoundError):
            pass


def start_expiry_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_expiring_certificates, "interval", hours=1)
    scheduler.add_job(check_expired_certificates, "interval", hours=1)
    scheduler.start()
