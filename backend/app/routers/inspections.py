from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from app.config.db import inspections_col, applications_col
from app.models.inspection import InspectionCreate, InspectionOut
from app.middleware.auth import role_required, get_current_user
from app.services.status_transition import (
    transition_status,
    InvalidTransitionError,
    ApplicationNotFoundError,
)
from app.services.cert_generator import issue_certificate

router = APIRouter(prefix="/api/v1/inspections", tags=["inspections"])


def to_inspection_out(doc: dict) -> InspectionOut:
    return InspectionOut(
        id=str(doc["_id"]),
        application_id=str(doc["application_id"]),
        officer_id=str(doc["officer_id"]),
        observations=doc["observations"],
        result=doc["result"],
        photos=doc.get("photos", []),
        inspected_at=doc["inspected_at"],
    )


@router.post("", response_model=InspectionOut, status_code=201)
def submit_inspection(
    payload: InspectionCreate,
    current_user: dict = Depends(role_required("lmo", "gatc")),
):
    try:
        app_oid = ObjectId(payload.application_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application_id")

    application = applications_col.find_one({"_id": app_oid})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.get("assigned_officer_id") != current_user["_id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only submit inspections for applications assigned to you",
        )

    if application["status"] != "scheduled":
        raise HTTPException(
            status_code=409,
            detail=f"Application must be in 'scheduled' status to inspect (currently '{application['status']}')",
        )

    doc = {
        "application_id": app_oid,
        "officer_id": current_user["_id"],
        "observations": payload.observations,
        "result": payload.result,
        "photos": payload.photos,
        "inspected_at": datetime.now(timezone.utc),
    }
    result = inspections_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Two-step transition: scheduled -> inspected -> certified/rejected.
    # Both steps go through the shared service so history stays complete
    # and Kiran's cron can trust the same audit trail.
    try:
        transition_status(app_oid, "inspected", meta={"changed_by": current_user["_id"]})
        final_status = "certified" if payload.result == "pass" else "rejected"
        transition_status(
            app_oid,
            final_status,
            meta={"changed_by": current_user["_id"], "reason": f"inspection result: {payload.result}"},
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApplicationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # A pass triggers certificate generation (Kiran's cert_generator).
    # This runs after the status is already 'certified' — if cert
    # generation fails for some reason (Cloudinary down, etc.), the
    # application stays correctly certified and this can be retried
    # manually, rather than the whole inspection call failing.
    if final_status == "certified":
        try:
            issue_certificate(doc["_id"])
        except Exception as e:
            # Don't fail the inspection submission over this — log and
            # move on. Surface it in your terminal so it isn't silently lost.
            print(f"[WARN] Certificate generation failed for inspection {doc['_id']}: {e}")

    return to_inspection_out(doc)


@router.get("/{inspection_id}", response_model=InspectionOut)
def get_inspection(
    inspection_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        doc = inspections_col.find_one({"_id": ObjectId(inspection_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid inspection id")

    if not doc:
        raise HTTPException(status_code=404, detail="Inspection not found")

    is_officer = current_user["role"] in ("lmo", "gatc") and doc["officer_id"] == current_user["_id"]
    is_admin = current_user["role"] == "admin"
    if not (is_officer or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this inspection")

    return to_inspection_out(doc)
