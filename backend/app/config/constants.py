# Single source of truth for enums used across models, routers and services.
# Keep these strings in sync with the frontend apps' shared constants file.

ROLES = ["owner", "lmo", "gatc", "admin"]

# owner accounts are open self-registration and usable immediately.
# lmo/gatc ("officer") accounts are invite-only: there is no public
# registration path for these roles at all. Only an admin can create one
# (routers/admin_users.py: POST /admin/users/create-officer), and the
# account is active the moment the admin creates it — the admin creating
# it *is* the approval. A generated temp password is shown to the admin
# once; the officer must change it on first login (see
# app/models/user.py: must_change_password).
#
# "pending"/"rejected" are kept in the enum for two reasons: (1) backward
# compatibility with any accounts created before this change, and (2) the
# admin can still use approve/reject on an existing officer account as a
# generic reactivate/suspend toggle (routers/admin_users.py). admin
# accounts are only ever created via the seed_super_admin.py script.
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