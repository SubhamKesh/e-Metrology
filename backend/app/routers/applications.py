from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument

from app.config.db import applications_col, instruments_col
import asyncio
from app.services.notifications import broadcast
from app.models.application import ApplicationCreate, ApplicationOut, HistoryEntry
from app.middleware.auth import get_current_user, role_required

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def _normalize_id(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


def _matches_user_id(doc_value, user_value) -> bool:
    return _normalize_id(doc_value) == _normalize_id(user_value)


def to_application_out(doc: dict) -> ApplicationOut:
    history = [
        HistoryEntry(
            status=h["to"],
            at=h["at"],
            by=str(h["changed_by"]) if h.get("changed_by") else None,
            note=h.get("reason"),
        )
        for h in doc.get("history", [])
    ]
    return ApplicationOut(
        id=str(doc["_id"]),
        instrument_id=str(doc["instrument_id"]),
        owner_id=str(doc["owner_id"]),
        status=doc["status"],
        assigned_officer_id=str(doc["assigned_officer_id"]) if doc.get("assigned_officer_id") else None,
        created_at=doc["submitted_at"],
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
    # Broadcast a lightweight event to connected officers so UIs can react in real-time.
    try:
        payload = {"type": "application_submitted", "application": to_application_out(doc).dict()}
        asyncio.create_task(broadcast(payload))
    except Exception:
        # don't fail the request if broadcasting fails
        pass
    return to_application_out(doc)


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status: Optional[str] = Query(default=None),
    mine: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    query: dict = {}
    user_id = current_user["_id"]
    user_id_str = str(user_id)

    if current_user["role"] == "owner":
        # Owners only ever see their own applications. Some historical records may
        # store owner_id as a string while newer ones use ObjectId, so match both.
        query["owner_id"] = {"$in": [user_id, user_id_str]}
    elif current_user["role"] in ("lmo", "gatc"):
        if mine:
            # "my assigned applications"
            query["assigned_officer_id"] = {"$in": [user_id, user_id_str]}
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
    is_owner = role == "owner" and _matches_user_id(doc.get("owner_id"), current_user["_id"])
    is_assigned_officer = role in ("lmo", "gatc") and _matches_user_id(doc.get("assigned_officer_id"), current_user["_id"])
    # Unassigned, still-submitted applications sit in the shared claim queue and must
    # stay visible to any lmo/gatc officer so they can open the detail page and claim
    # it — mirrors the queue query in list_applications() above.
    is_claimable_by_officer = (
        role in ("lmo", "gatc")
        and doc.get("assigned_officer_id") is None
        and doc.get("status") == "submitted"
    )
    is_admin = role == "admin"

    if not (is_owner or is_assigned_officer or is_claimable_by_officer or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this application")

    return to_application_out(doc)


@router.post("/{application_id}/claim", response_model=ApplicationOut)
def claim_application(
    application_id: str,
    current_user: dict = Depends(role_required("lmo", "gatc")),
):
    try:
        oid = ObjectId(application_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application id")

    now = datetime.now(timezone.utc)
    updated = applications_col.find_one_and_update(
        {"_id": oid, "status": "submitted", "assigned_officer_id": None},
        {
            "$set": {
                "assigned_officer_id": current_user["_id"],
                "status": "scheduled",
            },
            "$push": {
                "history": {
                    "from": "submitted",
                    "to": "scheduled",
                    "at": now,
                    "changed_by": current_user["_id"],
                }
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        doc = applications_col.find_one({"_id": oid})
        if not doc:
            raise HTTPException(status_code=404, detail="Application not found")
        if doc.get("assigned_officer_id") is not None:
            raise HTTPException(status_code=409, detail="Application already claimed by another officer")
        if doc.get("status") != "submitted":
            raise HTTPException(status_code=409, detail=f"Application is not claimable in status '{doc.get('status')}'")
        raise HTTPException(status_code=409, detail="Application is no longer claimable")

    return to_application_out(updated)
