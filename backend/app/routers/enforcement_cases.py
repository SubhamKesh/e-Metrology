"""Enforcement cases and notices (officer side) and the owner's view of notices addressed to them.

Officers (admin, LMO, GATC) open a case from the Oversight lists, send the owner a notice, add notes, escalate
to the next level or close it. The rules and the hourly clean-up live in services/enforcement_cases.py.

  POST /oversight/cases                  open a case for an instrument that is on a list (idempotent)
  GET  /oversight/cases                  the cases in the caller's jurisdiction (admin: all)
  GET  /oversight/cases/{id}             one case with its timeline
  POST /oversight/cases/{id}/notice      email + record a notice to the owner
  POST /oversight/cases/{id}/note        add a note
  POST /oversight/cases/{id}/escalate    pass it up one level
  POST /oversight/cases/{id}/close       close it with a reason
  GET  /notices/mine                     owner: notices on their instruments that are still open

Who may do what: anyone in the case's jurisdiction can read it and add a note; only the officer level that
holds the case (or an admin) can send a notice, escalate or close. Cases are read from the primary database
(an officer must see their own action on the next refresh); an owner's contact details are never returned.
"""
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from app.config.db import enforcement_cases_col, instruments_col, users_col
from app.config.settings import ESCALATION_AFTER_DAYS, NOTICE_MIN_GAP_DAYS
from app.middleware.auth import role_required
from app.models.enforcement_case import (
    CaseEventOut,
    CaseInstrument,
    CaseListItem,
    CaseListReport,
    CaseOut,
    CaseOwner,
    CasePermissions,
    CaseSummary,
    CloseIn,
    EscalateIn,
    NoteIn,
    NoticeIn,
    OpenCaseIn,
    OwnerNoticeOut,
)
from app.routers import oversight as ov
from app.services import audit as audit_service
from app.services import enforcement_cases as svc
from app.services import owner_notifications
from app.utils import search as search_utils

router = APIRouter(prefix="/api/v1/oversight/cases", tags=["enforcement-cases"])
notices_router = APIRouter(prefix="/api/v1/notices", tags=["enforcement-cases"])

OfficerRole = Annotated[dict, Depends(role_required("admin", "lmo", "gatc"))]
OwnerRole = Annotated[dict, Depends(role_required("owner"))]


# ---------------------------------------------------------------- helpers


def _oid(value: str, what: str = "Case") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail=f"{what} not found")


def _all(clauses: list[dict]) -> dict:
    clauses = [c for c in clauses if c]
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return svc.aware(dt).isoformat() if dt else None


def _notice_available_on(case: dict, now: datetime) -> Optional[date]:
    """While a recent notice blocks another one: the India date the next one may go out."""
    last = case.get("last_notice_at")
    if not last or not NOTICE_MIN_GAP_DAYS:
        return None
    on = svc.aware(last).astimezone(svc.IST).date() + timedelta(days=NOTICE_MIN_GAP_DAYS)
    return on if now.astimezone(svc.IST).date() < on else None


def _escalation_due(case: dict, now: datetime) -> bool:
    last = case.get("last_notice_at")
    return bool(
        case.get("active") and case.get("status") == "notice_sent" and last and case.get("level") != "admin"
        and svc.calendar_days(last, now) >= ESCALATION_AFTER_DAYS
    )


def _holds(case: dict, user: dict) -> bool:
    return bool(case.get("active")) and (user["role"] == "admin" or user["role"] == case.get("level"))


def _common(case: dict, user: dict, now: datetime, inst: dict, owner: dict, states: dict, districts: dict) -> dict:
    s, d = case.get("state_code"), case.get("district_code")
    return {
        "id": str(case["_id"]), "kind": case["kind"], "status": case["status"], "level": case["level"],
        "instrument": CaseInstrument(
            id=str(case["instrument_id"]), uiid=inst.get("uiid"), type=inst.get("type"),
            address_line=(inst.get("location") or {}).get("address_line"),
        ),
        "owner": CaseOwner(name=owner.get("name"), org_name=owner.get("org_name")),
        "state_name": states.get(s), "district_name": districts.get((s, d)),
        "opened_at": _iso(case.get("opened_at")), "last_notice_at": _iso(case.get("last_notice_at")),
        "notice_count": case.get("notice_count", 0), "escalation_due": _escalation_due(case, now),
        "resolved_at": _iso(case.get("resolved_at")), "resolution": case.get("resolution"),
        "held_by_me": bool(case.get("active")) and user["role"] == case.get("level"),
    }


def _lookups(cases: list[dict]):
    instrument_ids = [c["instrument_id"] for c in cases]
    instruments = {
        i["_id"]: i
        for i in instruments_col.find({"_id": {"$in": instrument_ids}}, {"uiid": 1, "type": 1, "owner_id": 1, "location.address_line": 1})
    } if cases else {}
    owner_ids = list({i.get("owner_id") for i in instruments.values() if i.get("owner_id")})
    owners = {u["_id"]: u for u in users_col.find({"_id": {"$in": owner_ids}}, {"name": 1, "org_name": 1})} if owner_ids else {}
    states, districts = ov._place_names({(c.get("state_code"), c.get("district_code")) for c in cases})
    return instruments, owners, states, districts


def _list_items(cases: list[dict], user: dict, now: datetime) -> list[CaseListItem]:
    instruments, owners, states, districts = _lookups(cases)
    out = []
    for c in cases:
        inst = instruments.get(c["instrument_id"], {})
        out.append(CaseListItem(**_common(c, user, now, inst, owners.get(inst.get("owner_id"), {}), states, districts)))
    return out


def _detail(case: dict, user: dict, now: datetime) -> CaseOut:
    instruments, owners, states, districts = _lookups([case])
    inst = instruments.get(case["instrument_id"], {})
    common = _common(case, user, now, inst, owners.get(inst.get("owner_id"), {}), states, districts)
    cert_no = valid_until = registered_on = None
    if case["kind"] == "lapsed":
        cert = svc.newest_certificate(case["instrument_id"])
        if cert:
            cert_no, valid_until = cert.get("cert_no"), _iso(cert["valid_until"])
    else:
        registered_on = _iso(case["instrument_id"].generation_time)
    available = _notice_available_on(case, now)
    holds = _holds(case, user)
    return CaseOut(
        **common,
        state_code=case.get("state_code"), district_code=case.get("district_code"),
        opened_by_name=case.get("opened_by_name"), escalation_after_days=ESCALATION_AFTER_DAYS,
        events=[
            CaseEventOut(
                at=_iso(e["at"]), action=e["action"], by_name=e.get("by_name"), by_role=e.get("by_role"),
                text=e.get("text"), to_level=e.get("to_level"), emailed=e.get("emailed"),
            )
            for e in case.get("events", [])
        ],
        can=CasePermissions(
            note=bool(case.get("active")), notice=holds and available is None,
            escalate=holds and svc.next_level(case["level"]) is not None, close=holds,
            notice_available_on=available.isoformat() if available else None,
        ),
        cert_no=cert_no, valid_until=valid_until, registered_on=registered_on,
    )


def _get_case(case_id: str, user: dict) -> dict:
    """The case if it exists and lies in the caller's jurisdiction (else 404, so out-of-scope ids reveal nothing)."""
    oid = _oid(case_id)
    case = enforcement_cases_col.find_one(ov._where(ov._scope(user), None, None, _id=oid))
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return svc.sync_case(case)


def _require_active(case: dict) -> None:
    if not case.get("active"):
        raise HTTPException(status_code=409, detail="This case is already resolved.")


def _require_holder(case: dict, user: dict) -> None:
    if not _holds(case, user):
        who = svc.ROLE_TITLE.get(case.get("level"), "another level")
        raise HTTPException(status_code=403, detail=f"This case is with the {who} now.")


# ---------------------------------------------------------------- open / list / read


@router.post("", response_model=CaseOut)
def open_case(payload: OpenCaseIn, request: Request, current_user: OfficerRole):
    """Open a case for an instrument on the lapsed or never-certified list. Opening twice returns the same case."""
    now = svc.now_utc()
    oid = _oid(payload.instrument_id, "Instrument")
    instrument = instruments_col.find_one(ov._where(ov._scope(current_user), None, None, prefix="location.", _id=oid))
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")

    existing = enforcement_cases_col.find_one({"instrument_id": oid, "active": True})
    if existing is not None:
        existing = svc.sync_case(existing, now)
        if existing.get("active"):
            return _detail(existing, current_user, now)

    kind = svc.classify(instrument, now)
    if kind is None:
        raise HTTPException(
            status_code=409,
            detail="This instrument is not on an enforcement list: it has a valid certificate, or it was "
                   "registered too recently to count as never certified.",
        )
    loc = instrument.get("location") or {}
    doc = {
        "instrument_id": oid, "owner_id": instrument.get("owner_id"), "kind": kind,
        "state_code": loc.get("state_code"), "district_code": loc.get("district_code"),
        "status": "open", "level": current_user["role"], "active": True,
        "opened_at": now, "opened_by": current_user["_id"], "opened_by_name": current_user.get("name") or current_user.get("email"),
        "last_notice_at": None, "notice_count": 0, "escalated_at": None,
        "resolved_at": None, "resolution": None, "updated_at": now,
        "events": [svc.event("opened", by=current_user, at=now)],
    }
    try:
        doc["_id"] = enforcement_cases_col.insert_one(doc).inserted_id
    except DuplicateKeyError:  # someone opened it a moment ago: use theirs
        found = enforcement_cases_col.find_one({"instrument_id": oid, "active": True})
        if found is None:
            raise HTTPException(status_code=409, detail="Could not open the case. Please try again.")
        return _detail(found, current_user, now)
    audit_service.log_event(
        "enforcement_case_opened", outcome="success", request=request,
        email=current_user.get("email"), user_id=str(current_user["_id"]), role=current_user["role"],
        detail=f"case={doc['_id']} instrument={instrument.get('uiid')} kind={kind}",
    )
    return _detail(doc, current_user, now)


@router.get("", response_model=CaseListReport)
def list_cases(
    current_user: OfficerRole,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
    status: Literal["active", "open", "notice_sent", "escalated", "resolved", "all"] = "active",
    kind: Optional[Literal["lapsed", "never_certified"]] = None,
    due: bool = False,
    with_me: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    now = svc.now_utc()
    place = ov._where(ov._scope(current_user), state_code, district_code)
    clauses = [place]
    if status == "active":
        clauses.append({"active": True})
    elif status == "resolved":
        clauses.append({"status": "resolved"})
    elif status != "all":
        clauses.append({"active": True, "status": status})
    if kind:
        clauses.append({"kind": kind})
    if due:
        clauses.append(svc.due_for_escalation_filter(now))
    if with_me:
        clauses.append({"active": True, "level": current_user["role"]})
    query = _all(clauses)

    total = enforcement_cases_col.count_documents(query) if query else enforcement_cases_col.count_documents({})
    cursor = enforcement_cases_col.find(query or {}).sort([("updated_at", -1), ("_id", -1)]).skip((page - 1) * page_size).limit(page_size)
    cases = [svc.sync_case(c, now) for c in cursor]

    count = lambda *extra: enforcement_cases_col.count_documents(_all([place, *extra]) or {})  # noqa: E731
    summary = CaseSummary(
        active=count({"active": True}),
        open=count({"active": True, "status": "open"}),
        notice_sent=count({"active": True, "status": "notice_sent"}),
        escalated=count({"active": True, "status": "escalated"}),
        escalation_due=count(svc.due_for_escalation_filter(now)),
        with_me=count({"active": True, "level": current_user["role"]}),
        resolved=count({"status": "resolved"}),
    )
    return CaseListReport(
        generated_at=now.isoformat(), summary=summary, total=total, page=page, page_size=page_size,
        items=_list_items(cases, current_user, now),
    )


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str, current_user: OfficerRole):
    return _detail(_get_case(case_id, current_user), current_user, svc.now_utc())


# ---------------------------------------------------------------- actions


@router.post("/{case_id}/notice", response_model=CaseOut)
def send_notice(case_id: str, payload: NoticeIn, request: Request, current_user: OfficerRole):
    """Record a notice to the owner and email it. The notice stays on record, and visible to the owner in
    the app, even when no email could be sent (`emailed` on the timeline says which)."""
    case = _get_case(case_id, current_user)
    _require_active(case)
    _require_holder(case, current_user)
    now = svc.now_utc()
    available = _notice_available_on(case, now)
    if available is not None:
        raise HTTPException(status_code=409, detail=f"A notice was sent recently. The next one can go out on {available:%d %b %Y}.")
    instrument = instruments_col.find_one({"_id": case["instrument_id"]})
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")

    message = (payload.message or "").strip() or None
    emailed = owner_notifications.can_email_owner(instrument.get("owner_id"))
    count = case.get("notice_count", 0)
    updated = enforcement_cases_col.find_one_and_update(
        {"_id": case["_id"], "active": True, "notice_count": count},
        {
            "$set": {"status": "notice_sent", "last_notice_at": now, "updated_at": now, "notice_count": count + 1},
            "$push": {"events": svc.event("notice", by=current_user, text=message, emailed=emailed, at=now)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This case just changed. Refresh and try again.")
    if emailed:  # after the record is safely written; never raises
        owner_notifications.notify_enforcement_notice(
            updated, instrument, dedupe_key=f"enforcement_notice:{case['_id']}:{count + 1}", message=message,
            issued_by=svc.ROLE_TITLE.get(current_user["role"], "Legal Metrology Department"),
            cert=svc.newest_certificate(instrument["_id"]) if case["kind"] == "lapsed" else None,
            registered_on=instrument["_id"].generation_time,
        )
    audit_service.log_event(
        "enforcement_notice_sent", outcome="success", request=request,
        email=current_user.get("email"), user_id=str(current_user["_id"]), role=current_user["role"],
        detail=f"case={case['_id']} n={count + 1} emailed={'yes' if emailed else 'no'}",
    )
    return _detail(updated, current_user, now)


@router.post("/{case_id}/note", response_model=CaseOut)
def add_note(case_id: str, payload: NoteIn, current_user: OfficerRole):
    case = _get_case(case_id, current_user)
    _require_active(case)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Write something in the note.")
    now = svc.now_utc()
    updated = enforcement_cases_col.find_one_and_update(
        {"_id": case["_id"], "active": True},
        {"$set": {"updated_at": now}, "$push": {"events": svc.event("note", by=current_user, text=text, at=now)}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This case just changed. Refresh and try again.")
    return _detail(updated, current_user, now)


@router.post("/{case_id}/escalate", response_model=CaseOut)
def escalate(case_id: str, payload: EscalateIn, current_user: OfficerRole):
    case = _get_case(case_id, current_user)
    _require_active(case)
    _require_holder(case, current_user)
    if svc.next_level(case["level"]) is None:
        raise HTTPException(status_code=409, detail="This case is already with the admin; there is nowhere higher to send it.")
    updated = svc.escalate_case(case, by=current_user, reason=(payload.reason or "").strip() or None)
    if updated is None:
        raise HTTPException(status_code=409, detail="This case just changed. Refresh and try again.")
    return _detail(updated, current_user, svc.now_utc())


@router.post("/{case_id}/close", response_model=CaseOut)
def close_case(case_id: str, payload: CloseIn, request: Request, current_user: OfficerRole):
    case = _get_case(case_id, current_user)
    _require_active(case)
    _require_holder(case, current_user)
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Give a reason for closing the case.")
    now = svc.now_utc()
    updated = enforcement_cases_col.find_one_and_update(
        {"_id": case["_id"], "active": True},
        {
            "$set": {"status": "resolved", "active": False, "resolved_at": now, "resolution": "closed", "updated_at": now},
            "$push": {"events": svc.event("resolved", by=current_user, text=reason, at=now)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This case just changed. Refresh and try again.")
    audit_service.log_event(
        "enforcement_case_closed", outcome="success", request=request,
        email=current_user.get("email"), user_id=str(current_user["_id"]), role=current_user["role"],
        detail=f"case={case['_id']}",
    )
    return _detail(updated, current_user, now)


# ---------------------------------------------------------------- owner: notices addressed to me


@notices_router.get("/mine", response_model=list[OwnerNoticeOut])
def my_notices(current_user: OwnerRole):
    """The latest notice on each of the owner's instruments whose case is still open. Names of officers and
    internal notes are not included, only the role that issued the notice."""
    owner_id = current_user["_id"]
    now = svc.now_utc()
    found = enforcement_cases_col.find(
        {"owner_id": {"$in": [owner_id, str(owner_id)]}, "active": True, "notice_count": {"$gt": 0}}
    ).sort("last_notice_at", -1).limit(50)
    cases = [c for c in (svc.sync_case(c, now) for c in found) if c.get("active")]
    instruments = {
        i["_id"]: i for i in instruments_col.find({"_id": {"$in": [c["instrument_id"] for c in cases]}}, {"uiid": 1, "type": 1})
    } if cases else {}
    out = []
    for c in cases:
        latest = next((e for e in reversed(c.get("events", [])) if e["action"] == "notice"), None)
        if latest is None:
            continue
        inst = instruments.get(c["instrument_id"], {})
        out.append(OwnerNoticeOut(
            case_id=str(c["_id"]), kind=c["kind"], instrument_id=str(c["instrument_id"]), uiid=inst.get("uiid"),
            instrument_type=inst.get("type"), sent_at=_iso(latest["at"]), message=latest.get("text"),
            issued_by=svc.ROLE_TITLE.get(latest.get("by_role"), "Legal Metrology Department"),
            notice_count=c.get("notice_count", 0),
        ))
    return out
