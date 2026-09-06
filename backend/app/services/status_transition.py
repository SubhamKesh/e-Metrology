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
