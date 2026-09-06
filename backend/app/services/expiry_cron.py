from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta

from app.config.db import certificates_col, alerts_col
from app.services.status_transition import mark_expiring, mark_expired, InvalidTransitionError, ApplicationNotFoundError


def check_expiring_certificates():
    """Certificates within 30 days of expiry: send a reminder (once) and
    move their application to 'expiring' if it's still 'certified'."""
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
