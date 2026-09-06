from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from app.config.db import certificates_collection, alerts_collection

# NOTE per contract: "nothing outside status_transition.py should ever
# set status directly." Import and call Deep's transition function here
# instead of writing to application["status"] yourself.
# from app.services.status_transition import mark_expiring, mark_expired


def check_expiring_certificates():
    soon = datetime.utcnow() + timedelta(days=30)
    expiring = certificates_collection.find({
        "valid_until": {"$lte": soon, "$gte": datetime.utcnow()}
    })

    for cert in expiring:
        exists = alerts_collection.find_one({
            "certificate_id": cert["_id"],
            "alert_type": "expiry_reminder",
        })
        if not exists:
            alerts_collection.insert_one({
                "certificate_id": cert["_id"],
                "alert_type": "expiry_reminder",
                "sent_at": datetime.utcnow(),
            })
        # mark_expiring(cert["inspection_id"])  # uncomment once Deep confirms this function


def check_expired_certificates():
    expired = certificates_collection.find({
        "valid_until": {"$lt": datetime.utcnow()}
    })
    for cert in expired:
        pass
        # mark_expired(cert["inspection_id"])  # uncomment once Deep confirms this function


def start_expiry_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_expiring_certificates, "interval", hours=1)
    scheduler.add_job(check_expired_certificates, "interval", hours=1)
    scheduler.start()