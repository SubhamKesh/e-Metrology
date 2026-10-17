from datetime import datetime, timedelta, timezone
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Response
from pymongo.errors import DuplicateKeyError

from app.config.db import inspections_col, applications_col, instruments_col
from app.config.inspection_forms import form_spec
from app.config.instrument_specs import INSTRUMENT_SPECS
from app.models.inspection import InspectionCreate, InspectionOut
from app.services.inspection_form import build_form_fields
from app.middleware.auth import role_required, get_current_user
from app.services.status_transition import (
    transition_status,
    InvalidTransitionError,
    ApplicationNotFoundError,
)
from app.services.jobs import start_certificate_generation
from app.services.owner_notifications import notify_inspection_result

router = APIRouter(prefix="/api/v1/inspections", tags=["inspections"])

# An offline inspection may reach the server late. captured_at is trusted as the
# inspection time only inside this window (never in the future, never ancient);
# otherwise the server clock is used. The server receipt time is always kept.
MAX_OFFLINE_AGE = timedelta(days=14)
CLOCK_SKEW = timedelta(minutes=5)


def _inspection_time(captured_at: datetime | None, now: datetime) -> tuple[datetime, bool]:
    """Returns (inspected_at, submitted_offline)."""
    if captured_at is None:
        return now, False
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)
    if captured_at > now + CLOCK_SKEW or captured_at < now - MAX_OFFLINE_AGE:
        return now, False
    captured_at = min(captured_at, now)
    return captured_at, (now - captured_at) > timedelta(seconds=60)


def to_inspection_out(doc: dict, *, for_owner: bool = False) -> InspectionOut:
    form = doc.get("form")
    return InspectionOut(
        id=str(doc["_id"]),
        application_id=str(doc["application_id"]),
        # An owner sees the result and the evidence, not who the officer was or where they stood.
        officer_id=None if for_owner else str(doc["officer_id"]),
        observations=doc["observations"],
        result=doc["result"],
        photos=doc.get("photos", []),
        identity_method=doc.get("identity_method", "manual"),
        location=None if for_owner else doc.get("location"),
        seal_number=doc.get("seal_number"),
        test_points=doc.get("test_points", []),
        checks=doc.get("checks", []),
        form={k: form[k] for k in ("instrument_type", "unit", "test_title", "reference_label", "indicated_label")} if form else None,
        submitted_offline=doc.get("submitted_offline", False),
        created_at=doc["inspected_at"],
    )


@router.get("/form-spec")
def get_form_spec(
    type: str,
    current_user: dict = Depends(role_required("lmo", "gatc", "admin")),
):
    """What to record for one instrument type: test readings, checks, seal number."""
    if type not in INSTRUMENT_SPECS:
        raise HTTPException(status_code=404, detail="Unknown instrument type")
    return form_spec(type)


@router.get("/by-application/{application_id}", response_model=InspectionOut)
def get_inspection_for_application(
    application_id: str,
    current_user: dict = Depends(get_current_user),
):
    """The latest inspection of an application. Officer (own inspection) and admin see everything;
    the instrument's owner sees the result and evidence without the officer or GPS position."""
    try:
        app_oid = ObjectId(application_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application id")
    application = applications_col.find_one({"_id": app_oid})
    doc = inspections_col.find_one({"application_id": app_oid}, sort=[("inspected_at", -1)])
    if not application or not doc:
        raise HTTPException(status_code=404, detail="No inspection recorded for this application")

    role = current_user["role"]
    if role == "admin":
        return to_inspection_out(doc)
    if role in ("lmo", "gatc") and doc["officer_id"] == current_user["_id"]:
        return to_inspection_out(doc)
    if role == "owner" and application.get("owner_id") == current_user["_id"]:
        return to_inspection_out(doc, for_owner=True)
    raise HTTPException(status_code=403, detail="Not authorized to view this inspection")


@router.post("", response_model=InspectionOut, status_code=201)
def submit_inspection(
    payload: InspectionCreate,
    response: Response,
    current_user: dict = Depends(role_required("lmo", "gatc")),
):
    try:
        app_oid = ObjectId(payload.application_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application_id")

    # Idempotent replay: the same officer re-sending the same client_id (a retry after a
    # lost response, or a queued offline inspection syncing twice) gets the original
    # record back and nothing is applied again.
    if payload.client_id:
        existing = inspections_col.find_one({"officer_id": current_user["_id"], "client_id": payload.client_id})
        if existing:
            response.status_code = 200
            return to_inspection_out(existing)

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

    instrument = instruments_col.find_one({"_id": application.get("instrument_id")}, {"type": 1})
    form_fields = build_form_fields(payload, instrument.get("type") if instrument else None)
    if form_fields.get("seal_number") and inspections_col.find_one({"seal_number": form_fields["seal_number"]}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Seal number already used on another inspection. Check the number on the seal.")

    now = datetime.now(timezone.utc)
    inspected_at, offline = _inspection_time(payload.captured_at, now)
    doc = {
        "application_id": app_oid,
        "officer_id": current_user["_id"],
        "observations": payload.observations,
        "result": payload.result,
        "photos": payload.photos,
        "identity_method": payload.identity_method,
        "location": payload.location.model_dump(),
        "inspected_at": inspected_at,
        "received_at": now,
        "submitted_offline": offline,
        **form_fields,
    }
    if payload.client_id:
        doc["client_id"] = payload.client_id
    try:
        result = inspections_col.insert_one(doc)
    except DuplicateKeyError:
        # Two concurrent syncs of the same inspection: the unique index let one through.
        existing = (
            inspections_col.find_one({"officer_id": current_user["_id"], "client_id": payload.client_id})
            if payload.client_id else None
        )
        if existing:
            response.status_code = 200
            return to_inspection_out(existing)
        if form_fields.get("seal_number"):
            # Lost a race for the same seal number to another officer.
            raise HTTPException(status_code=409, detail="Seal number already used on another inspection. Check the number on the seal.")
        raise
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

    # Email the owner the inspection outcome (pass -> certified, fail -> rejected).
    # The certificate itself gets its own email once it has been generated.
    notify_inspection_result(application, doc)

    # A pass triggers certificate generation. The status is already
    # 'certified' by now, so a generation failure never fails the inspection;
    # it is retried in the background and can be re-issued with
    # POST /certificates/generate/{application_id}. start_certificate_generation
    # uses the RQ worker only if one is actually running, otherwise a
    # background thread -- see app/services/jobs.py.
    if final_status == "certified":
        start_certificate_generation(doc["_id"])

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
