from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from app.config.db import instruments_col, applications_col, certificates_col, inspections_col
from app.models.dashboard import OwnerDashboard, OfficerDashboard, AdminDashboard, NextExpiry, StateBreakdown
from app.middleware.auth import role_required

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Statuses considered "pending" — still moving through the workflow, no outcome yet.
PENDING_STATUSES = ["submitted", "scheduled", "inspected"]
# Statuses considered "verified" — a valid certificate currently exists.
VERIFIED_STATUSES = ["certified", "expiring"]


@router.get("/owner", response_model=OwnerDashboard)
def owner_dashboard(current_user: dict = Depends(role_required("owner"))):
    owner_id = current_user["_id"]

    total_instruments = instruments_col.count_documents({"owner_id": owner_id})
    verified = applications_col.count_documents({"owner_id": owner_id, "status": {"$in": VERIFIED_STATUSES}})
    pending = applications_col.count_documents({"owner_id": owner_id, "status": {"$in": PENDING_STATUSES}})
    expired = applications_col.count_documents({"owner_id": owner_id, "status": "expired"})

    owner_app_ids = [a["_id"] for a in applications_col.find({"owner_id": owner_id}, {"_id": 1})]
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


def _officer_dashboard_data(officer_id) -> OfficerDashboard:
    """Shared logic for /lmo and /gatc — same shape, scoped to whichever
    officer is calling. Frontend hits these as two separate paths
    (DashboardApi.lmo() / DashboardApi.gatc()) rather than one shared
    /dashboard/officer, so both routes below call this helper directly."""
    assigned = applications_col.count_documents({"assigned_officer_id": officer_id})
    pending = applications_col.count_documents({"assigned_officer_id": officer_id, "status": "scheduled"})
    completed = applications_col.count_documents(
        {"assigned_officer_id": officer_id, "status": {"$in": ["certified", "rejected"]}}
    )

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_inspections = inspections_col.count_documents(
        {"officer_id": officer_id, "inspected_at": {"$gte": today_start}}
    )

    return OfficerDashboard(
        assigned=assigned,
        pending=pending,
        completed=completed,
        today_inspections=today_inspections,
    )


@router.get("/lmo", response_model=OfficerDashboard)
def lmo_dashboard(current_user: dict = Depends(role_required("lmo"))):
    return _officer_dashboard_data(current_user["_id"])


@router.get("/gatc", response_model=OfficerDashboard)
def gatc_dashboard(current_user: dict = Depends(role_required("gatc"))):
    return _officer_dashboard_data(current_user["_id"])


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
