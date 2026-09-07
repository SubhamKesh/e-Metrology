from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from app.config.db import instruments_col, applications_col
from app.models.instrument import ALLOWED_INSTRUMENT_TYPES, InstrumentCreate, InstrumentOut
from app.middleware.auth import get_current_user, role_required
from app.services.uiid_generator import generate_uiid

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


def _normalize_id(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _can_view_instrument_for_assigned_application(doc: dict, current_user: dict) -> bool:
    if current_user["role"] not in ("lmo", "gatc"):
        return False

    current_user_id = current_user["_id"]
    current_user_id_str = str(current_user_id)
    instrument_id = doc["_id"]

    # Either the officer is already assigned to an application for this
    # instrument, or the instrument belongs to an unclaimed application
    # still sitting in the shared queue (visible to any lmo/gatc, mirroring
    # applications.py's own queue/claim visibility rules).
    app = applications_col.find_one(
        {
            "instrument_id": instrument_id,
            "$or": [
                {"assigned_officer_id": {"$in": [current_user_id, current_user_id_str]}},
                {"assigned_officer_id": None, "status": "submitted"},
            ],
        }
    )
    return app is not None


def to_instrument_out(doc: dict) -> InstrumentOut:
    return InstrumentOut(
        id=str(doc["_id"]),
        owner_id=str(doc["owner_id"]),
        uiid=doc["uiid"],
        type=doc["type"],
        manufacturer=doc["manufacturer"],
        model=doc["model"],
        capacity=doc["capacity"],
        serial_no=doc["serial_no"],
        location=doc.get("location"),
    )


@router.post("", response_model=InstrumentOut, status_code=201)
def register_instrument(
    payload: InstrumentCreate,
    current_user: dict = Depends(role_required("owner")),
):
    # Belt-and-suspenders on top of the Pydantic Literal check on
    # InstrumentCreate.type: guards against the type being widened later
    # (e.g. someone loosens the model back to `str`) without this check
    # being updated in step.
    if payload.type not in ALLOWED_INSTRUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid instrument type")

    doc = {
        "owner_id": current_user["_id"],
        "uiid": generate_uiid(),
        "type": payload.type,
        "manufacturer": payload.manufacturer,
        "model": payload.model,
        "capacity": payload.capacity,
        "serial_no": payload.serial_no,
        "location": payload.location,
    }

    try:
        result = instruments_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An instrument with this serial number already exists")

    doc["_id"] = result.inserted_id
    return to_instrument_out(doc)


@router.get("", response_model=list[InstrumentOut])
def list_instruments(
    owner_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    # Owners only ever see their own instruments, regardless of query param.
    # Admins can see all, or filter down to a specific owner via ?owner_id=
    if current_user["role"] == "owner":
        query = {"owner_id": current_user["_id"]}
    elif current_user["role"] == "admin":
        query = {}
        if owner_id:
            try:
                query["owner_id"] = ObjectId(owner_id)
            except InvalidId:
                raise HTTPException(status_code=400, detail="Invalid owner_id")
    else:
        # lmo/gatc don't browse the full instrument list directly —
        # they reach instruments via their assigned applications instead.
        raise HTTPException(status_code=403, detail="Not authorized for this action")

    docs = instruments_col.find(query)
    return [to_instrument_out(doc) for doc in docs]


@router.get("/{instrument_id}", response_model=InstrumentOut)
def get_instrument(
    instrument_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        doc = instruments_col.find_one({"_id": ObjectId(instrument_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid instrument id")

    if not doc:
        raise HTTPException(status_code=404, detail="Instrument not found")

    is_owner = current_user["role"] == "owner" and _normalize_id(doc.get("owner_id")) == _normalize_id(current_user["_id"])
    is_admin = current_user["role"] == "admin"
    is_assigned_officer = _can_view_instrument_for_assigned_application(doc, current_user)
    if not (is_owner or is_admin or is_assigned_officer):
        raise HTTPException(status_code=403, detail="Not authorized to view this instrument")

    return to_instrument_out(doc)


@router.get("/by-uiid/{uiid}", response_model=InstrumentOut)
def get_instrument_by_uiid(
    uiid: str,
    current_user: dict = Depends(role_required("lmo", "gatc", "admin")),
):
    """
    Lookup by UIID instead of Mongo _id — this is what an officer's QR
    scan resolves to in the field-verification flow (scan -> get UIID ->
    fetch the registered instrument -> compare serial number physically).
    """
    doc = instruments_col.find_one({"uiid": uiid})
    if not doc:
        raise HTTPException(status_code=404, detail="No instrument registered with this UIID")
    return to_instrument_out(doc)