from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config.db import applications_col, instruments_col
from app.models.application import ApplicationCreate, ApplicationOut, HistoryEntry
from app.middleware.auth import get_current_user, role_required
from app.services.status_transition import (
    transition_status,
    InvalidTransitionError,
    ApplicationNotFoundError,
)

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def to_application_out(doc: dict) -> ApplicationOut:
    history = [
        HistoryEntry(
            from_status=h.get("from"),
            to=h["to"],
            at=h["at"],
            changed_by=str(h["changed_by"]) if h.get("changed_by") else None,
            reason=h.get("reason"),
        )
        for h in doc.get("history", [])
    ]
    return ApplicationOut(
        id=str(doc["_id"]),
        instrument_id=str(doc["instrument_id"]),
        owner_id=str(doc["owner_id"]),
        status=doc["status"],
        assigned_officer_id=str(doc["assigned_officer_id"]) if doc.get("assigned_officer_id") else None,
        submitted_at=doc["submitted_at"],
        history=history,
    )


@router.post("", response_model=ApplicationOut, status_code=201)
def submit_application(
    payload: ApplicationCreate,
    current_user: dict = Depends(role_required("owner")),
):
    try:
        instrument_oid = ObjectId(payload.instrument_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid instrument_id")

    instrument = instruments_col.find_one({"_id": instrument_oid})
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    if instrument["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=403, detail="You can only apply for your own instruments")

    doc = {
        "instrument_id": instrument_oid,
        "owner_id": current_user["_id"],
        "status": "submitted",
        "assigned_officer_id": None,
        "submitted_at": datetime.now(timezone.utc),
        "history": [
            {"from": None, "to": "submitted", "at": datetime.now(timezone.utc)}
        ],
    }

    result = applications_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return to_application_out(doc)


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status: Optional[str] = Query(default=None),
    mine: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    query: dict = {}

    if current_user["role"] == "owner":
        # Owners only ever see their own applications.
        query["owner_id"] = current_user["_id"]
    elif current_user["role"] in ("lmo", "gatc"):
        if mine:
            # "my assigned applications"
            query["assigned_officer_id"] = current_user["_id"]
        else:
            # the claimable queue — unassigned, still submitted
            query["status"] = "submitted"
            query["assigned_officer_id"] = None
    # admin sees everything by default, optionally filtered by status below

    if status:
        query["status"] = status

    docs = applications_col.find(query).sort("submitted_at", -1)
    return [to_application_out(doc) for doc in docs]


@router.get("/{application_id}", response_model=ApplicationOut)
def get_application(
    application_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        doc = applications_col.find_one({"_id": ObjectId(application_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application id")

    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    role = current_user["role"]
    is_owner = role == "owner" and doc["owner_id"] == current_user["_id"]
    is_assigned_officer = role in ("lmo", "gatc") and doc.get("assigned_officer_id") == current_user["_id"]
    is_admin = role == "admin"

    if not (is_owner or is_assigned_officer or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this application")

    return to_application_out(doc)


@router.post("/{application_id}/claim", response_model=ApplicationOut)
def claim_application(
    application_id: str,
    current_user: dict = Depends(role_required("lmo", "gatc")),
):
    try:
        doc = applications_col.find_one({"_id": ObjectId(application_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application id")

    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    if doc.get("assigned_officer_id") is not None:
        raise HTTPException(status_code=409, detail="Application already claimed by another officer")

    # Assign the officer first, then transition the status.
    applications_col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"assigned_officer_id": current_user["_id"]}},
    )

    try:
        updated = transition_status(
            doc["_id"],
            "scheduled",
            meta={"changed_by": current_user["_id"]},
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApplicationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return to_application_out(updated)
