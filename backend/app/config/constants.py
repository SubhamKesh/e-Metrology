# Single source of truth for enums used across models, routers and services.
# Keep these strings in sync with the frontend apps' shared constants file.

ROLES = ["owner", "lmo", "gatc", "admin"]

APPLICATION_STATUS = [
    "submitted",
    "scheduled",
    "inspected",
    "certified",
    "rejected",
    "expiring",
    "expired",
]

# Which statuses a given status is allowed to move to.
# Enforced by services/status_transition.py so no code path can skip a step
# or set an illegal status directly.
ALLOWED_TRANSITIONS = {
    "submitted": ["scheduled"],
    "scheduled": ["inspected"],
    "inspected": ["certified", "rejected"],
    "certified": ["expiring"],
    "expiring": ["expired"],
    "rejected": [],
    "expired": [],
}
