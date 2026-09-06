from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from app.config.db import instruments_col
from app.models.instrument import InstrumentCreate, InstrumentOut
from app.middleware.auth import get_current_user, role_required

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


def to_instrument_out(doc: dict) -> InstrumentOut:
    return InstrumentOut(
        id=str(doc["_id"]),
        owner_id=str(doc["owner_id"]),
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
    doc = {
        "owner_id": current_user["_id"],
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

    is_owner = current_user["role"] == "owner" and doc["owner_id"] == current_user["_id"]
    is_admin = current_user["role"] == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this instrument")

    return to_instrument_out(doc)
