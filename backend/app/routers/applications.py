from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument

from app.config.db import applications_col, certificates_col, instruments_col, users_col
from app.config.settings import REVERIFY_WINDOW_DAYS
from app.models.instrument import ALLOWED_INSTRUMENT_TYPES
from app.services.notifications import broadcast_threadsafe
from app.services.owner_notifications import (
    notify_application_submitted,
    notify_application_scheduled,
    notify_application_rescheduled,
)
from app.services import scheduling
from app.models.application import (
    ApplicationCreate, ApplicationOut, AssignIn, HistoryEntry, ScheduleHistoryOut, ScheduleIn,
)
from app.middleware.auth import get_current_user, role_required, jurisdiction_filter
from app.utils import search as search_utils

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _normalize_id(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


def _matches_user_id(doc_value, user_value) -> bool:
    return _normalize_id(doc_value) == _normalize_id(user_value)


def _oid(value: str, what: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {what}")


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
        state_code=doc.get("state_code", "unknown"),
        district_code=doc.get("district_code", "unknown"),
        application_type=doc.get("application_type") or "initial",
        previous_certificate_id=doc.get("previous_certificate_id"),
        previous_cert_no=doc.get("previous_cert_no"),
        previous_valid_until=_as_utc(doc["previous_valid_until"]) if doc.get("previous_valid_until") else None,
        scheduled_date=doc.get("scheduled_date"),
        slot=doc.get("slot"),
        slot_label=scheduling.slot_label(doc.get("slot")),
        schedule_history=[
            ScheduleHistoryOut(
                kind=h["kind"], date=h["date"], slot=h["slot"], at=_as_utc(h["at"]),
                by=str(h["by"]) if h.get("by") else None, reason=h.get("reason"),
                previous_date=(h.get("previous") or {}).get("date"),
                previous_slot=(h.get("previous") or {}).get("slot"),
            )
            for h in doc.get("schedule_history", [])
        ],
    )


# An instrument can only have one application in flight at a time.
_OPEN_STATUSES = ["submitted", "scheduled", "inspected"]


def _resolve_previous_certificate(instrument_oid, requested_id: Optional[str]) -> dict | None:
    """The certificate this application renews, or None for a first verification.

    A requested id must belong to this very instrument (422 otherwise). With no
    id, the instrument's newest certificate is used, so every application for an
    instrument that has been certified before is a renewal.
    """
    if requested_id:
        cert = certificates_col.find_one({"_id": requested_id, "instrument_id": instrument_oid})
        if not cert:
            raise HTTPException(status_code=422, detail="That certificate does not belong to this instrument")
        return cert
    return certificates_col.find_one({"instrument_id": instrument_oid}, sort=[("valid_until", -1)])


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

    location = instrument.get("location") or {}
    if not location.get("state_code") or not location.get("district_code"):
        # Legacy instrument registered before structured location existed —
        # can't route it to a jurisdiction. Surface this loudly instead of
        # silently writing a broken application that no officer queue will
        # ever match.
        raise HTTPException(
            status_code=422,
            detail="Instrument is missing state_code/district_code — update its location before applying",
        )

    if applications_col.find_one({"instrument_id": instrument_oid, "status": {"$in": _OPEN_STATUSES}}):
        raise HTTPException(
            status_code=409,
            detail="This instrument already has an application in progress. Wait for it to finish before applying again.",
        )

    # Re-verification opens REVERIFY_WINDOW_DAYS before the current certificate expires
    # and stays open afterwards. Earlier than that there is nothing to renew yet.
    newest = certificates_col.find_one({"instrument_id": instrument_oid}, sort=[("valid_until", -1)])
    newest_valid_until = _as_utc(newest["valid_until"]) if newest else None
    if newest_valid_until:
        opens_on = newest_valid_until - timedelta(days=REVERIFY_WINDOW_DAYS)
        if datetime.now(timezone.utc) < opens_on:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This instrument's certificate is valid until {newest_valid_until.strftime('%d %b %Y')}. "
                    f"You can apply for re-verification from {opens_on.strftime('%d %b %Y')}."
                ),
            )

    previous = _resolve_previous_certificate(instrument_oid, payload.previous_certificate_id)

    doc = {
        "instrument_id": instrument_oid,
        "owner_id": current_user["_id"],
        "application_type": "renewal" if previous else "initial",
        "previous_certificate_id": previous["_id"] if previous else None,
        "previous_cert_no": previous.get("cert_no") if previous else None,
        # When the instrument's current certificate runs out; the officer queue uses it for priority.
        "previous_valid_until": newest_valid_until,
        "status": "submitted",
        "assigned_officer_id": None,
        "submitted_at": datetime.now(timezone.utc),
        # Denormalized from the instrument so every downstream jurisdiction
        # filter (officer queue, dashboards) is a plain indexed match.
        "state_code": location["state_code"],
        "district_code": location["district_code"],
        "history": [
            {"from": None, "to": "submitted", "at": datetime.now(timezone.utc)}
        ],
    }

    result = applications_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    # Broadcast a lightweight event to connected officers so UIs can react in real-time.
    # This route is a plain `def` (FastAPI runs it in a threadpool, not on
    # the event loop) -- broadcast_threadsafe(), not asyncio.create_task(),
    # is what correctly schedules the coroutine from here. See
    # services/notifications.py's module docstring for why the two aren't
    # interchangeable (this used to silently no-op every single call).
    try:
        payload = {"type": "application_submitted", "application": to_application_out(doc).dict()}
        # Only the owner it belongs to, officers whose jurisdiction covers
        # this state/district, and admins should see this -- not every
        # connected client (see _should_deliver in services/notifications.py).
        audience = {
            "owner_id": str(doc["owner_id"]),
            "state_code": doc["state_code"],
            "district_code": doc["district_code"],
        }
        broadcast_threadsafe(payload, audience)
    except Exception:
        # don't fail the request if broadcasting fails
        pass
    # Email the owner that the application was received (best-effort).
    notify_application_submitted(doc)
    return to_application_out(doc)


def find_applications(
    current_user: dict,
    status: Optional[str] = None,
    mine: bool = False,
    q: Optional[str] = None,
    application_type: Optional[str] = None,
    instrument_type: Optional[str] = None,
    state_code: Optional[str] = None,
    district_code: Optional[str] = None,
    date_from=None,
    date_to=None,
) -> list[dict]:
    """The applications this user may see, narrowed by the optional search filters.

    Used by GET /applications and by the report export, so a downloaded report always holds exactly
    what the list shows. Who may see what (`scope`) is decided first and can never be widened by a
    filter: filters are ANDed on top of it.
    """
    scope: dict = {}
    user_id = current_user["_id"]
    user_id_str = str(user_id)

    if current_user["role"] == "owner":
        # Owners only ever see their own applications. Some historical records may
        # store owner_id as a string while newer ones use ObjectId, so match both.
        scope["owner_id"] = {"$in": [user_id, user_id_str]}
    elif current_user["role"] in ("lmo", "gatc"):
        if mine:
            # "my assigned applications" — already scoped by assignment,
            # no need to also filter by jurisdiction (an officer can only
            # ever be assigned something inside their own scope anyway,
            # since claim_application enforces that — see below).
            scope["assigned_officer_id"] = {"$in": [user_id, user_id_str]}
        else:
            # The claimable queue — unassigned, still submitted, AND inside
            # this officer's jurisdiction. Without the jurisdiction filter
            # here, an LMO in one district would see (and be able to claim)
            # applications meant for a completely different state.
            scope["status"] = "submitted"
            scope["assigned_officer_id"] = None
            scope.update(jurisdiction_filter(current_user))
    # admin sees everything by default, optionally filtered by status below

    if status:
        scope["status"] = status

    extra: list[dict] = []
    text = search_utils.clean_query(q)
    search_utils.check_instrument_type(instrument_type, ALLOWED_INSTRUMENT_TYPES)
    if application_type:
        # Records from before re-verification existed have no type and count as initial.
        extra.append({"application_type": "renewal"} if application_type == "renewal"
                     else {"application_type": {"$ne": "renewal"}})
    if state_code:
        extra.append({"state_code": state_code})
    if district_code:
        extra.append({"district_code": district_code})
    window = search_utils.ist_window(date_from, date_to)
    if window:
        extra.append({"submitted_at": window})

    # Instrument-based filters (free text and type) resolve to the matching instruments first;
    # an application does not carry the instrument's own fields.
    inst_filter = search_utils.instrument_filter(None, instrument_type)
    if inst_filter:
        ids = [i["_id"] for i in instruments_col.find(inst_filter, {"_id": 1}).limit(search_utils.MAX_INSTRUMENT_MATCHES)]
        extra.append({"instrument_id": {"$in": ids}})
    if text:
        or_clauses: list[dict] = [{"previous_cert_no": search_utils.contains(text)}]
        text_filter = search_utils.instrument_filter(text)
        ids = [i["_id"] for i in instruments_col.find(text_filter, {"_id": 1}).limit(search_utils.MAX_INSTRUMENT_MATCHES)]
        if ids:
            or_clauses.append({"instrument_id": {"$in": ids}})
        try:
            or_clauses.append({"_id": ObjectId(text)})  # the full application id
        except (InvalidId, TypeError):
            pass
        extra.append({"$or": or_clauses})

    query = search_utils.combine(scope, extra)
    docs = list(applications_col.find(query).sort("submitted_at", -1))
    if current_user["role"] in ("lmo", "gatc") and not mine:
        # Claimable queue: re-verifications first, the one whose certificate runs out
        # soonest (or ran out longest ago) at the top; first-time applications after.
        def _key(d):
            expiry = d.get("previous_valid_until")
            return (0, _as_utc(expiry).timestamp()) if expiry else (1, -_as_utc(d["submitted_at"]).timestamp())

        docs.sort(key=_key)
    return docs


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status: Optional[str] = Query(default=None),
    mine: bool = Query(default=False),
    q: search_utils.SearchText = None,
    application_type: Annotated[Optional[Literal["initial", "renewal"]], Query()] = None,
    instrument_type: search_utils.InstrumentTypeParam = None,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
    date_from: search_utils.DateFrom = None,
    date_to: search_utils.DateTo = None,
    current_user: dict = Depends(get_current_user),
):
    """Applications this user may see. All search filters are optional and combine with AND:
    `q` matches the instrument's UIID, serial number, manufacturer, model or type, the certificate
    number being renewed, or the full application id; the dates are India calendar days of submission."""
    docs = find_applications(
        current_user, status=status, mine=mine, q=q, application_type=application_type,
        instrument_type=instrument_type, state_code=state_code, district_code=district_code,
        date_from=date_from, date_to=date_to,
    )
    return [to_application_out(doc) for doc in docs]


@router.get("/slots")
def slot_availability(
    officer_id: Optional[str] = Query(default=None, description="Required for admins; officers see their own"),
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD, defaults to today"),
    days: int = Query(default=14, ge=1, le=62),
    current_user: dict = Depends(role_required("lmo", "gatc", "admin")),
):
    """Places left per date and slot for one officer, so the UI only offers bookable slots."""
    if current_user["role"] == "admin":
        if not officer_id:
            raise HTTPException(status_code=422, detail="officer_id is required")
        officer_oid = _oid(officer_id, "officer id")
    else:
        # An officer can only look at their own diary.
        officer_oid = current_user["_id"]
        if officer_id and officer_id != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="You can only view your own slot availability")
    first = scheduling.parse_date(start) if start else scheduling.today_ist()
    return {
        "officer_id": str(officer_oid),
        "capacity_per_slot": scheduling.settings.SLOT_CAPACITY_PER_OFFICER,
        "days": scheduling.availability(applications_col, officer_oid, first, days),
    }


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
    jf = jurisdiction_filter(current_user)
    is_claimable_by_officer = (
        role in ("lmo", "gatc")
        and doc.get("assigned_officer_id") is None
        and doc.get("status") == "submitted"
        and all(doc.get(k) == v for k, v in jf.items())
    )
    is_admin = role == "admin"

    if not (is_owner or is_assigned_officer or is_claimable_by_officer or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this application")

    return to_application_out(doc)


def _release_if_overbooked(oid, officer_id, day: str, slot: str, restore: dict) -> None:
    """Two requests can pass the capacity check for the last place at once. After the
    write we count again; if the slot is over capacity this write is undone."""
    if scheduling.slot_still_within_capacity(applications_col, officer_id, day, slot):
        return
    applications_col.update_one({"_id": oid, "scheduled_date": day, "slot": slot}, restore)
    raise HTTPException(status_code=409, detail="That slot was just filled. Pick another slot or date.")


@router.post("/{application_id}/claim", response_model=ApplicationOut)
def claim_application(
    application_id: str,
    payload: ScheduleIn,
    current_user: dict = Depends(role_required("lmo", "gatc")),
):
    """Take an application from the queue and book its inspection date and slot."""
    oid = _oid(application_id, "application id")
    officer_id = current_user["_id"]
    scheduling.check_bookable(applications_col, officer_id, payload.date, payload.slot)

    now = datetime.now(timezone.utc)
    # Jurisdiction check baked into the same atomic filter as the claim
    # itself — an officer can't claim outside their scope even by guessing
    # an application_id directly (defense in depth beyond the queue filter
    # in list_applications above).
    claim_filter = {
        "_id": oid,
        "status": "submitted",
        "assigned_officer_id": None,
        **jurisdiction_filter(current_user),
    }
    updated = applications_col.find_one_and_update(
        claim_filter,
        {
            "$set": {
                "assigned_officer_id": officer_id,
                "status": "scheduled",
                "scheduled_date": payload.date,
                "slot": payload.slot,
            },
            "$push": {
                "history": {
                    "from": "submitted",
                    "to": "scheduled",
                    "at": now,
                    "changed_by": officer_id,
                    "reason": f"Inspection booked for {payload.date}, {payload.slot}",
                },
                "schedule_history": scheduling.history_entry("scheduled", payload.date, payload.slot, officer_id, None),
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
        jf = jurisdiction_filter(current_user)
        if jf and any(doc.get(k) != v for k, v in jf.items()):
            raise HTTPException(status_code=403, detail="Application is outside your jurisdiction")
        raise HTTPException(status_code=409, detail="Application is no longer claimable")

    _release_if_overbooked(
        oid, officer_id, payload.date, payload.slot,
        {
            "$set": {"assigned_officer_id": None, "status": "submitted", "scheduled_date": None, "slot": None},
            "$pop": {"history": 1, "schedule_history": 1},
        },
    )
    # Email the owner that an officer has been assigned, with the date and slot (best-effort).
    notify_application_scheduled(updated)
    return to_application_out(updated)


@router.post("/{application_id}/schedule", response_model=ApplicationOut)
def reschedule_application(
    application_id: str,
    payload: ScheduleIn,
    current_user: dict = Depends(role_required("lmo", "gatc", "admin")),
):
    """Change the date or slot of an inspection that is already booked.

    The assigned officer or an admin can do it. Only while the application is still
    `scheduled`; once inspected there is nothing left to move."""
    oid = _oid(application_id, "application id")
    doc = applications_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if current_user["role"] != "admin" and not _matches_user_id(doc.get("assigned_officer_id"), current_user["_id"]):
        raise HTTPException(status_code=403, detail="Only the assigned officer or an admin can reschedule this inspection")
    if doc.get("status") != "scheduled":
        raise HTTPException(status_code=409, detail=f"Only a scheduled inspection can be rescheduled (status is '{doc.get('status')}')")
    if doc.get("scheduled_date") == payload.date and doc.get("slot") == payload.slot:
        raise HTTPException(status_code=409, detail="The inspection is already booked for that date and slot")

    officer_id = doc["assigned_officer_id"]
    scheduling.check_bookable(applications_col, officer_id, payload.date, payload.slot, exclude_application=oid)

    previous = {"date": doc.get("scheduled_date"), "slot": doc.get("slot")}
    updated = applications_col.find_one_and_update(
        {"_id": oid, "status": "scheduled", "assigned_officer_id": officer_id},
        {
            "$set": {"scheduled_date": payload.date, "slot": payload.slot},
            "$push": {"schedule_history": scheduling.history_entry(
                "rescheduled", payload.date, payload.slot, current_user["_id"], payload.reason, previous)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="The application changed while you were rescheduling. Reload and try again.")

    _release_if_overbooked(
        oid, officer_id, payload.date, payload.slot,
        {"$set": {"scheduled_date": previous["date"], "slot": previous["slot"]}, "$pop": {"schedule_history": 1}},
    )
    notify_application_rescheduled(updated, previous_date=previous["date"], previous_slot=previous["slot"], reason=payload.reason)
    return to_application_out(updated)


@router.post("/{application_id}/assign", response_model=ApplicationOut)
def assign_application(
    application_id: str,
    payload: AssignIn,
    current_user: dict = Depends(role_required("admin")),
):
    """Admin allocates an application to a named officer with a date and slot.

    Works on a `submitted` application (first assignment) and on a `scheduled` one
    (move it to another officer). The officer must be active and the application must
    sit inside their jurisdiction."""
    oid = _oid(application_id, "application id")
    officer_oid = _oid(payload.officer_id, "officer id")

    doc = applications_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if doc.get("status") not in ("submitted", "scheduled"):
        raise HTTPException(status_code=409, detail=f"Cannot assign an application in status '{doc.get('status')}'")

    officer = users_col.find_one({"_id": officer_oid, "role": {"$in": ["lmo", "gatc"]}})
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found")
    if officer.get("status", "active") != "active":
        raise HTTPException(status_code=409, detail="That officer account is not active")
    jf = jurisdiction_filter(officer)
    if not jf or any(doc.get(k) != v for k, v in jf.items()):
        raise HTTPException(status_code=422, detail="This application is outside that officer's jurisdiction")

    scheduling.check_bookable(applications_col, officer_oid, payload.date, payload.slot, exclude_application=oid)

    first_time = doc["status"] == "submitted"
    previous = None if first_time else {
        "date": doc.get("scheduled_date"), "slot": doc.get("slot"), "officer_id": str(doc.get("assigned_officer_id")),
    }
    now = datetime.now(timezone.utc)
    update: dict = {
        "$set": {"assigned_officer_id": officer_oid, "status": "scheduled",
                 "scheduled_date": payload.date, "slot": payload.slot},
        "$push": {"schedule_history": scheduling.history_entry(
            "assigned" if first_time else "reassigned", payload.date, payload.slot,
            current_user["_id"], payload.reason, previous)},
    }
    if first_time:
        update["$push"]["history"] = {
            "from": "submitted", "to": "scheduled", "at": now, "changed_by": current_user["_id"],
            "reason": f"Assigned by admin; inspection booked for {payload.date}, {payload.slot}",
        }
    updated = applications_col.find_one_and_update(
        {"_id": oid, "status": doc["status"], "assigned_officer_id": doc.get("assigned_officer_id")},
        update,
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="The application changed while you were assigning it. Reload and try again.")

    restore: dict = {"$pop": {"schedule_history": 1}}
    if first_time:
        restore["$set"] = {"assigned_officer_id": None, "status": "submitted", "scheduled_date": None, "slot": None}
        restore["$pop"]["history"] = 1
    else:
        restore["$set"] = {"assigned_officer_id": doc.get("assigned_officer_id"),
                           "scheduled_date": previous["date"], "slot": previous["slot"]}
    _release_if_overbooked(oid, officer_oid, payload.date, payload.slot, restore)

    if first_time:
        notify_application_scheduled(updated)
    else:
        notify_application_rescheduled(updated, previous_date=previous["date"], previous_slot=previous["slot"],
                                       reason=payload.reason or "Your inspection was reassigned to another officer")
    return to_application_out(updated)
