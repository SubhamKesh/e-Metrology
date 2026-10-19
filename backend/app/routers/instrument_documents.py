"""Required documents for an instrument's verification application.

  GET    /api/v1/instruments/{id}/documents         the document slots, which are required, and what is uploaded
  POST   /api/v1/instruments/{id}/documents/{slot}  upload (or replace) one slot (owner of the instrument only)
  DELETE /api/v1/instruments/{id}/documents/{slot}  remove one slot (owner only)

Slots (services/documents.py): first verification needs a Tax invoice and an Owner ID proof;
a re-verification needs the Previous certificate. One file per slot; uploading again replaces it.
PDF, JPG or PNG, up to 5 MB, checked by content. The owner cannot change documents while an
application for the instrument is open. Every upload and removal is audited.
"""
from datetime import datetime, timezone
import re
import uuid

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.config.db import applications_col, certificates_col, instrument_documents_col, instruments_col
from app.middleware.auth import get_current_user, role_required
from app.models.document import DocumentOut, DocumentSlotOut, DocumentSlotsOut
from app.routers.instruments import _can_view_instrument_for_assigned_application, _normalize_id
from app.services import documents as docs
from app.services.audit import log_event
from app.utils.file_checks import DOCUMENT_KINDS as ALLOWED_FILE_KINDS
from app.utils.file_checks import EXTENSION, MAX_DOCUMENT_BYTES, MIME, read_checked
from app.utils.upload_to_cloudinary import upload_bytes

router = APIRouter(prefix="/api/v1/instruments/{instrument_id}/documents", tags=["instrument-documents"])

# Same list as routers/applications.py: an application in any of these states is being processed.
_OPEN_STATUSES = ["submitted", "scheduled", "inspected"]


def _oid(value: str, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {what}")


def _instrument(instrument_id: str) -> dict:
    doc = instruments_col.find_one({"_id": _oid(instrument_id, "instrument id")})
    if not doc:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return doc


def _owns(instrument: dict, user: dict) -> bool:
    return user["role"] == "owner" and _normalize_id(instrument.get("owner_id")) == _normalize_id(user["_id"])


def _newest_certificate(instrument: dict) -> dict | None:
    return certificates_col.find_one({"instrument_id": instrument["_id"]}, sort=[("valid_until", -1)])


def _is_locked(instrument: dict) -> bool:
    return applications_col.find_one({"instrument_id": instrument["_id"], "status": {"$in": _OPEN_STATUSES}}) is not None


def _clean_filename(name: str | None, kind: str) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]).strip(" .")[:80]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return f"{stem or 'document'}.{EXTENSION[kind]}"


def to_document_out(doc: dict) -> DocumentOut:
    return DocumentOut(
        id=str(doc["_id"]), instrument_id=str(doc["instrument_id"]), slot=doc["slot"],
        label=docs.SLOT_LABEL.get(doc["slot"], doc["slot"]), filename=doc["filename"],
        content_type=doc["content_type"], size=int(doc["size"]), url=doc["url"], uploaded_at=doc["uploaded_at"],
    )


def _slots_out(instrument: dict) -> DocumentSlotsOut:
    newest = _newest_certificate(instrument)
    have = docs.current_documents(instrument["_id"], newest)
    required = docs.required_slots(newest)
    # Required slots first; any other document already on file is shown after them, not required.
    order = list(required) + [s for s in docs.SLOT_LABEL if s not in required and s in have]
    return DocumentSlotsOut(
        application_type="renewal" if newest else "initial",
        complete=all(s in have for s in required),
        locked=_is_locked(instrument),
        slots=[
            DocumentSlotOut(
                slot=s, label=docs.SLOT_LABEL[s], hint=docs.SLOT_HINT[s], required=s in required,
                document=to_document_out(have[s]) if s in have else None,
            )
            for s in order
        ],
    )


@router.get("", response_model=DocumentSlotsOut)
def list_documents(instrument_id: str, current_user: dict = Depends(get_current_user)):
    instrument = _instrument(instrument_id)
    allowed = (
        _owns(instrument, current_user)
        or current_user["role"] == "admin"
        or _can_view_instrument_for_assigned_application(instrument, current_user)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized to view this instrument's documents")
    return _slots_out(instrument)


def _editable_slot(instrument: dict, slot: str, user: dict) -> None:
    if not _owns(instrument, user):
        raise HTTPException(status_code=403, detail="You can only change documents of your own instruments")
    if slot not in docs.SLOT_LABEL:
        raise HTTPException(status_code=404, detail="Unknown document type")
    if slot not in docs.required_slots(_newest_certificate(instrument)):
        raise HTTPException(status_code=422, detail=f"{docs.SLOT_LABEL[slot]} is not needed for this application.")
    if _is_locked(instrument):
        raise HTTPException(
            status_code=409, detail="This instrument has an application in progress, so its documents can't be changed."
        )


@router.post("/{slot}", response_model=DocumentOut, status_code=201)
async def upload_document(
    instrument_id: str,
    slot: str,
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(role_required("owner")),
):
    instrument = _instrument(instrument_id)
    _editable_slot(instrument, slot, current_user)
    data, file_kind = await read_checked(file, ALLOWED_FILE_KINDS, MAX_DOCUMENT_BYTES, "document")
    is_pdf = file_kind == "pdf"
    public_id = f"doc_{instrument['_id']}_{slot}_{uuid.uuid4().hex[:10]}" + (".pdf" if is_pdf else "")
    try:
        url = upload_bytes(data, public_id=public_id, resource_type="raw" if is_pdf else "image")
    except Exception:
        raise HTTPException(status_code=502, detail="The document could not be saved right now. Please try again.")
    doc = {
        "instrument_id": instrument["_id"], "owner_id": current_user["_id"], "slot": slot,
        "filename": _clean_filename(file.filename, file_kind), "content_type": MIME[file_kind], "size": len(data),
        "url": url, "uploaded_at": datetime.now(timezone.utc),
    }
    # One file per slot: this replaces whatever was there.
    instrument_documents_col.delete_many({"instrument_id": instrument["_id"], "slot": slot})
    doc["_id"] = instrument_documents_col.insert_one(doc).inserted_id
    log_event(
        "document_uploaded", outcome="success", request=request, email=current_user["email"],
        user_id=str(current_user["_id"]), role="owner", detail=f"instrument={instrument.get('uiid')} slot={slot}",
    )
    return to_document_out(doc)


@router.delete("/{slot}", status_code=204)
def delete_document(instrument_id: str, slot: str, request: Request, current_user: dict = Depends(role_required("owner"))):
    instrument = _instrument(instrument_id)
    _editable_slot(instrument, slot, current_user)
    result = instrument_documents_col.delete_many({"instrument_id": instrument["_id"], "slot": slot})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    log_event(
        "document_deleted", outcome="success", request=request, email=current_user["email"],
        user_id=str(current_user["_id"]), role="owner", detail=f"instrument={instrument.get('uiid')} slot={slot}",
    )
