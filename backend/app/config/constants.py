# Single source of truth for enums used across models, routers and services.
# Keep these strings in sync with the frontend apps' shared constants file.

ROLES = ["owner", "lmo", "gatc", "admin"]

# owner accounts are usable immediately on registration. lmo/gatc accounts
# start "pending" and can't log in until an admin (the department head /
# minister account) approves them — see routers/auth.py login() and the
# new routers/admin_users.py approve/reject endpoints. admin accounts are
# only ever created via the seed_super_admin.py script, never through
# self-registration, so they're always "active".
USER_STATUS = ["pending", "active", "rejected"]

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