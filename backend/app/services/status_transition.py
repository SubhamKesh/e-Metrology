"""
Single source of truth for changing an Application's status.

Nobody — not routers, not Kiran's cron job — should ever do
applications_col.update_one({"_id": ...}, {"$set": {"status": ...}})
directly. Everything goes through transition_status() so:
  1. illegal jumps (e.g. submitted -> certified) are rejected
  2. every change is recorded in the application's history[] for audit
  3. there's exactly one place to debug if statuses ever look wrong
"""

from datetime import datetime, timezone
from bson import ObjectId
from app.config.db import applications_col
from app.config.constants import ALLOWED_TRANSITIONS


class InvalidTransitionError(Exception):
    """Raised when a status change isn't allowed from the current status."""
    pass


class ApplicationNotFoundError(Exception):
    pass


def transition_status(application_id: str, new_status: str, meta: dict | None = None) -> dict:
    """
    Moves an application to new_status if the transition is legal.

    application_id: string or ObjectId of the application
    new_status: must be one of app.config.constants.APPLICATION_STATUS
    meta: optional dict merged into the history entry — e.g.
          {"changed_by": user_id, "reason": "inspection failed"}

    Returns the updated application document.
    Raises InvalidTransitionError / ApplicationNotFoundError on failure.
    """
    oid = application_id if isinstance(application_id, ObjectId) else ObjectId(application_id)

    application = applications_col.find_one({"_id": oid})
    if not application:
        raise ApplicationNotFoundError(f"No application with id {application_id}")

    current_status = application["status"]
    allowed = ALLOWED_TRANSITIONS.get(current_status, [])

    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot move application from '{current_status}' to '{new_status}'. "
            f"Allowed next steps: {allowed or 'none — this is a terminal status'}"
        )

    history_entry = {
        "from": current_status,
        "to": new_status,
        "at": datetime.now(timezone.utc),
        **(meta or {}),
    }

    applications_col.update_one(
        {"_id": oid},
        {
            "$set": {"status": new_status},
            "$push": {"history": history_entry},
        },
    )

    return applications_col.find_one({"_id": oid})


def mark_expiring(application_id, reason: str = "certificate entering expiry window") -> dict:
    """
    Convenience wrapper for expiry_cron.py — moves certified -> expiring.
    Silently no-ops (returns the current doc unchanged) if the application
    isn't in 'certified' status, since the cron may see the same cert
    across multiple runs before it actually needs to transition.
    """
    oid = application_id if isinstance(application_id, ObjectId) else ObjectId(application_id)
    application = applications_col.find_one({"_id": oid})
    if not application:
        raise ApplicationNotFoundError(f"No application with id {application_id}")
    if application["status"] != "certified":
        return application
    return transition_status(oid, "expiring", meta={"reason": reason})


def mark_expired(application_id, reason: str = "certificate valid_until has passed") -> dict:
    """
    Convenience wrapper for expiry_cron.py — moves expiring -> expired.
    Same no-op behavior as mark_expiring if not currently 'expiring'.
    """
    oid = application_id if isinstance(application_id, ObjectId) else ObjectId(application_id)
    application = applications_col.find_one({"_id": oid})
    if not application:
        raise ApplicationNotFoundError(f"No application with id {application_id}")
    if application["status"] != "expiring":
        return application
    return transition_status(oid, "expired", meta={"reason": reason})
