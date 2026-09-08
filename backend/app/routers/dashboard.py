from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from app.config.db import instruments_col, applications_col, certificates_col, inspections_col, users_col
from app.models.dashboard import OwnerDashboard, OfficerDashboard, AdminDashboard, NextExpiry, StateBreakdown
from app.middleware.auth import role_required

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Statuses considered "pending" — still moving through the workflow, no outcome yet.
PENDING_STATUSES = ["submitted", "scheduled", "inspected"]
# Statuses considered "verified" — a valid certificate currently exists.
VERIFIED_STATUSES = ["certified", "expiring"]


@router.get("/owner", response_model=OwnerDashboard)
def owner_dashboard(current_user: dict = Depends(role_required("owner", allow_admin_view=True))):
    # Admin (the minister) sees this same view aggregated across every owner
    # system-wide, not a single arbitrary owner's numbers — matches how
    # /dashboard/admin already reports globally. A real owner gets the
    # normal scoped-to-them behavior, unchanged.
    is_admin_view = current_user["role"] == "admin"
    owner_filter: dict = {} if is_admin_view else {"owner_id": current_user["_id"]}

    total_instruments = instruments_col.count_documents(owner_filter)
    verified = applications_col.count_documents({**owner_filter, "status": {"$in": VERIFIED_STATUSES}})
    pending = applications_col.count_documents({**owner_filter, "status": {"$in": PENDING_STATUSES}})
    expired = applications_col.count_documents({**owner_filter, "status": "expired"})

    owner_app_ids = [a["_id"] for a in applications_col.find(owner_filter, {"_id": 1})]
    next_expiry = None
    if owner_app_ids:
        cert = certificates_col.find(
            {"application_id": {"$in": owner_app_ids}, "valid_until": {"$gte": datetime.now(timezone.utc)}}
        ).sort("valid_until", 1).limit(1)
        cert = next(cert, None)
        if cert:
            instrument = instruments_col.find_one({"_id": cert["instrument_id"]})
            valid_until = cert["valid_until"]
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            days_remaining = (valid_until - datetime.now(timezone.utc)).days
            next_expiry = NextExpiry(
                instrument_type=instrument["type"] if instrument else "Unknown",
                uiid=instrument["uiid"] if instrument else "Unknown",
                valid_until=valid_until.isoformat(),
                days_remaining=days_remaining,
            )

    return OwnerDashboard(
        total_instruments=total_instruments,
        verified=verified,
        pending=pending,
        expired=expired,
        next_expiry=next_expiry,
    )


def _officer_dashboard_data(officer_filter: dict, inspector_filter: dict) -> OfficerDashboard:
    """Shared logic for /lmo and /gatc — same shape. `officer_filter` scopes
    applications by assigned_officer_id (a single officer for a normal
    lmo/gatc user, or "any officer of this role" for the admin aggregate
    view below). `inspector_filter` does the same for inspections.officer_id."""
    assigned = applications_col.count_documents({**officer_filter})
    pending = applications_col.count_documents({**officer_filter, "status": "scheduled"})
    completed = applications_col.count_documents(
        {**officer_filter, "status": {"$in": ["certified", "rejected"]}}
    )

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_inspections = inspections_col.count_documents(
        {**inspector_filter, "inspected_at": {"$gte": today_start}}
    )

    return OfficerDashboard(
        assigned=assigned,
        pending=pending,
        completed=completed,
        today_inspections=today_inspections,
    )


def _officer_ids_for_role(role: str) -> list:
    """All user _ids currently holding `role` — used to build the
    admin-aggregate filters below (system-wide totals for that role,
    not one arbitrary officer's numbers)."""
    return [u["_id"] for u in users_col.find({"role": role}, {"_id": 1})]


def _dashboard_for_role(role: str, current_user: dict) -> OfficerDashboard:
    if current_user["role"] == "admin":
        officer_ids = _officer_ids_for_role(role)
        officer_filter = {"assigned_officer_id": {"$in": officer_ids}}
        inspector_filter = {"officer_id": {"$in": officer_ids}}
    else:
        officer_filter = {"assigned_officer_id": current_user["_id"]}
        inspector_filter = {"officer_id": current_user["_id"]}
    return _officer_dashboard_data(officer_filter, inspector_filter)


@router.get("/lmo", response_model=OfficerDashboard)
def lmo_dashboard(current_user: dict = Depends(role_required("lmo", allow_admin_view=True))):
    return _dashboard_for_role("lmo", current_user)


@router.get("/gatc", response_model=OfficerDashboard)
def gatc_dashboard(current_user: dict = Depends(role_required("gatc", allow_admin_view=True))):
    return _dashboard_for_role("gatc", current_user)


@router.get("/admin", response_model=AdminDashboard)
def admin_dashboard(current_user: dict = Depends(role_required("admin"))):
    total_instruments = instruments_col.count_documents({})
    verified = applications_col.count_documents({"status": {"$in": VERIFIED_STATUSES}})
    pending = applications_col.count_documents({"status": {"$in": PENDING_STATUSES}})
    expired = applications_col.count_documents({"status": "expired"})

    pipeline = [
        {"$group": {"_id": "$location", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_location = [
        StateBreakdown(location=row["_id"] or "Unspecified", count=row["count"])
        for row in instruments_col.aggregate(pipeline)
    ]

    return AdminDashboard(
        total_instruments=total_instruments,
        verified=verified,
        pending=pending,
        expired=expired,
        by_location=by_location,
    )