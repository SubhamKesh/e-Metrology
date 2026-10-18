"""CSV and PDF report downloads.

Each endpoint returns the same rows as the matching list screen, with the same search filters, as a
file. Nothing here decides who may see what: the rows come from the list helpers
(`find_applications`, `find_certificates`, `find_instruments`) and the audit viewer's own query, which
apply the role and jurisdiction rules first. A filter can only narrow, never widen.

  GET /reports/applications   owner (own), officer (queue or `mine=true`), admin (all)
  GET /reports/certificates   owner (own), officer (jurisdiction), admin (all)
  GET /reports/instruments    owner (own), admin (all)
  GET /reports/audit-logs     admin

`format=csv` (default) or `format=pdf`. At most REPORT_MAX_ROWS rows (newest first); when more match,
the file holds the newest ones and the response says so in `X-Report-Total` / `X-Report-Truncated`
(and the PDF prints a note). Every download is written to the audit log.
"""

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.config.db import (
    applications_col, certificates_col, districts_col, instruments_col, read_replica, states_col, users_col,
)
from app.config.settings import EXPIRY_REMINDER_DAYS, REPORT_MAX_ROWS
from app.middleware.auth import get_current_user, role_required
from app.rate_limit import RATE_LIMIT_REPORTS, limiter
from app.routers import admin_audit
from app.routers.applications import find_applications
from app.routers.certificates import find_certificates
from app.routers.instruments import find_instruments
from app.services import audit as audit_service
from app.services import report_export as rx
from app.services.report_export import Column, Report
from app.utils import search as search_utils

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Format = Annotated[Literal["csv", "pdf"], Query(description="File type")]

_EXPOSE = "Content-Disposition, X-Report-Rows, X-Report-Total, X-Report-Truncated"


# --- shared helpers -------------------------------------------------------------------------------

def _label(value: Optional[str]) -> str:
    return (value or "").replace("_", " ").capitalize()


def _generated_by(user: dict) -> str:
    who = user.get("name") or user.get("email") or ""
    role = {"owner": "Business owner", "lmo": "Legal Metrology Officer", "gatc": "GATC", "admin": "Admin"}.get(user.get("role"), "")
    return f"{who} ({role})" if who and role else who


def _filters(*pairs: tuple[str, Any]) -> list[tuple[str, str]]:
    """The filters that were actually used, for the PDF header."""
    return [(label, str(value)) for label, value in pairs if value not in (None, "", False)]


def _range_text(date_from, date_to) -> Optional[str]:
    if not date_from and not date_to:
        return None
    return f"{rx.fmt_date(date_from) if date_from else 'start'} to {rx.fmt_date(date_to) if date_to else 'today'}"


def _place_lookup(pairs: set[tuple[Optional[str], Optional[str]]]):
    """(state_code, district_code) -> (state name, district name); a code with no match stays as the code."""
    state_codes = {s for s, _ in pairs if s}
    states = {s["code"]: s["name"] for s in states_col.find({"code": {"$in": list(state_codes)}})} if state_codes else {}
    districts = (
        {(d["state_code"], d["code"]): d["name"] for d in districts_col.find({"state_code": {"$in": list(state_codes)}})}
        if state_codes else {}
    )

    def lookup(state: Optional[str], district: Optional[str]) -> tuple[str, str]:
        return states.get(state, state or ""), districts.get((state, district), district or "")

    return lookup


def _owner_orgs(owner_ids) -> dict:
    ids = list({o for o in owner_ids if o})
    if not ids:
        return {}
    return {
        u["_id"]: (u.get("org_name") or u.get("name") or "")
        for u in users_col.find({"_id": {"$in": ids}}, {"org_name": 1, "name": 1})
    }


def _cert_status(valid_until, now: datetime) -> str:
    if not valid_until:
        return ""
    valid_until = rx._as_utc(valid_until)
    if valid_until < now:
        return "Expired"
    if (valid_until - now).days < max(EXPIRY_REMINDER_DAYS):
        return "Expiring soon"
    return "Valid"


def _deliver(report: Report, fmt: str, kind: str, user: dict, request: Request) -> Response:
    body, media_type, ext = rx.render(report, fmt)
    audit_service.log_event(
        "report_exported", outcome="success", request=request,
        email=user.get("email"), user_id=str(user["_id"]), role=user.get("role"),
        detail=f"{kind} {fmt} rows={len(report.rows)} total={report.total}",
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{rx.file_stem(kind)}.{ext}"',
        # Personal and operational data: never keep a copy in a shared or intermediate cache.
        "Cache-Control": "no-store",
        "X-Report-Rows": str(len(report.rows)),
        "X-Report-Total": str(report.total if report.total is not None else len(report.rows)),
        "X-Report-Truncated": "true" if report.truncated else "false",
        "Access-Control-Expose-Headers": _EXPOSE,
    }
    return Response(content=body, media_type=media_type, headers=headers)


def _build(title: str, columns: list[Column], rows: list[dict], total: int, filters, user: dict) -> Report:
    return Report(
        title=title, columns=columns, rows=rows, filters=filters, total=total,
        generated_by=_generated_by(user), generated_at=datetime.now(timezone.utc),
    )


# --- applications ---------------------------------------------------------------------------------

@router.get("/applications")
@limiter.limit(RATE_LIMIT_REPORTS)
def applications_report(
    request: Request,
    format: Format = "csv",
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
    """Applications report. Same rows and filters as GET /applications."""
    docs = find_applications(
        current_user, status=status, mine=mine, q=q, application_type=application_type,
        instrument_type=instrument_type, state_code=state_code, district_code=district_code,
        date_from=date_from, date_to=date_to,
    )
    total = len(docs)
    docs = docs[:REPORT_MAX_ROWS]

    instruments = {i["_id"]: i for i in instruments_col.find({"_id": {"$in": [d["instrument_id"] for d in docs]}})}
    is_admin = current_user["role"] == "admin"
    officers = owners = {}
    if is_admin:
        officers = {
            u["_id"]: u.get("name", "")
            for u in users_col.find({"_id": {"$in": [d["assigned_officer_id"] for d in docs if d.get("assigned_officer_id")]}}, {"name": 1})
        }
        owners = _owner_orgs(d.get("owner_id") for d in docs)
    place = _place_lookup({(d.get("state_code"), d.get("district_code")) for d in docs})

    rows = []
    for d in docs:
        inst = instruments.get(d["instrument_id"]) or {}
        state, district = place(d.get("state_code"), d.get("district_code"))
        rows.append({
            "id": str(d["_id"]),
            "type": "Re-verification" if d.get("application_type") == "renewal" else "First verification",
            "status": _label(d.get("status")),
            "uiid": inst.get("uiid", ""),
            "instrument_type": inst.get("type", ""),
            "manufacturer": inst.get("manufacturer", ""),
            "model": inst.get("model", ""),
            "serial_no": inst.get("serial_no", ""),
            "state": state,
            "district": district,
            "applied_on": rx.fmt_datetime(d.get("submitted_at")),
            "inspection_date": rx.fmt_date(d.get("scheduled_date")),
            "slot": _label(d.get("slot")),
            "renews": d.get("previous_cert_no") or "",
            "previous_valid_until": rx.fmt_date(d.get("previous_valid_until")),
            "officer": officers.get(d.get("assigned_officer_id"), ""),
            "owner": owners.get(d.get("owner_id"), ""),
        })

    columns = [
        Column("id", "Application ID", weight=2.6),
        Column("type", "Type", weight=1.3),
        Column("status", "Status", weight=1.0),
        Column("uiid", "Instrument UIID", weight=1.3),
        Column("instrument_type", "Instrument type", weight=1.8),
        Column("manufacturer", "Manufacturer", in_pdf=False),
        Column("model", "Model", in_pdf=False),
        Column("serial_no", "Serial no.", in_pdf=False),
        Column("state", "State", weight=1.3),
        Column("district", "District", weight=1.3),
        Column("applied_on", "Applied on", weight=1.4),
        Column("inspection_date", "Inspection date", weight=1.2),
        Column("slot", "Slot", in_pdf=False),
        Column("renews", "Renews certificate", in_pdf=False),
        Column("previous_valid_until", "Previous certificate valid until", in_pdf=False),
    ]
    if is_admin:
        columns += [Column("officer", "Assigned officer", in_pdf=False), Column("owner", "Owner organisation", in_pdf=False)]

    filters = _filters(
        ("Status", _label(status)), ("My applications", mine and current_user["role"] in ("lmo", "gatc")),
        ("Search", search_utils.clean_query(q)),
        ("Type", {"initial": "First verification", "renewal": "Re-verification"}.get(application_type)),
        ("Instrument type", instrument_type), ("State", state_code), ("District", district_code),
        ("Applied", _range_text(date_from, date_to)),
    )
    report = _build("Applications report", columns, rows, total, filters, current_user)
    return _deliver(report, format, "applications", current_user, request)


# --- certificates ---------------------------------------------------------------------------------

@router.get("/certificates")
@limiter.limit(RATE_LIMIT_REPORTS)
def certificates_report(
    request: Request,
    format: Format = "csv",
    q: search_utils.SearchText = None,
    status: Annotated[Optional[Literal["valid", "expiring", "expired"]], Query()] = None,
    application_type: Annotated[Optional[Literal["initial", "renewal"]], Query()] = None,
    instrument_type: search_utils.InstrumentTypeParam = None,
    date_from: search_utils.DateFrom = None,
    date_to: search_utils.DateTo = None,
    current_user: dict = Depends(get_current_user),
):
    """Certificates report. Same rows and filters as GET /certificates."""
    certs, instruments = find_certificates(
        current_user, q=q, status=status, application_type=application_type, instrument_type=instrument_type,
        date_from=date_from, date_to=date_to,
    )
    total = len(certs)
    certs = certs[:REPORT_MAX_ROWS]

    is_admin = current_user["role"] == "admin"
    owners = {}
    if is_admin:
        owner_of_app = {
            a["_id"]: a.get("owner_id")
            for a in applications_col.find({"_id": {"$in": [c["application_id"] for c in certs]}}, {"owner_id": 1})
        }
        orgs = _owner_orgs(owner_of_app.values())
        owners = {app_id: orgs.get(owner_id, "") for app_id, owner_id in owner_of_app.items()}
    place = _place_lookup({
        ((instruments.get(c.get("instrument_id")) or {}).get("location", {}).get("state_code"),
         (instruments.get(c.get("instrument_id")) or {}).get("location", {}).get("district_code"))
        for c in certs
    })

    now = datetime.now(timezone.utc)
    rows = []
    for c in certs:
        inst = instruments.get(c.get("instrument_id")) or {}
        loc = inst.get("location") or {}
        state, district = place(loc.get("state_code"), loc.get("district_code"))
        rows.append({
            "cert_no": c.get("cert_no") or c["_id"],
            "status": _cert_status(c.get("valid_until"), now),
            "uiid": inst.get("uiid", ""),
            "instrument_type": inst.get("type", ""),
            "manufacturer": inst.get("manufacturer", ""),
            "model": inst.get("model", ""),
            "serial_no": inst.get("serial_no", ""),
            "seal_number": c.get("seal_number") or "",
            "state": state,
            "district": district,
            "kind": "Re-verification" if c.get("application_type") == "renewal" else "First verification",
            "renews": c.get("previous_cert_no") or "",
            "verified_on": rx.fmt_date(c.get("issued_at")),
            "valid_from": rx.fmt_date(c.get("valid_from") or c.get("issued_at")),
            "valid_until": rx.fmt_date(c.get("valid_until")),
            "owner": owners.get(c.get("application_id"), ""),
        })

    columns = [
        Column("cert_no", "Certificate no.", weight=2.0),
        Column("status", "Status", weight=1.1),
        Column("uiid", "Instrument UIID", weight=1.3),
        Column("instrument_type", "Instrument type", weight=1.8),
        Column("manufacturer", "Manufacturer", in_pdf=False),
        Column("model", "Model", in_pdf=False),
        Column("serial_no", "Serial no.", in_pdf=False),
        Column("seal_number", "Seal / stamp no.", weight=1.4),
        Column("state", "State", weight=1.3),
        Column("district", "District", weight=1.3),
        Column("kind", "Type", in_pdf=False),
        Column("renews", "Renews certificate", in_pdf=False),
        Column("verified_on", "Verified on", weight=1.2),
        Column("valid_from", "Valid from", in_pdf=False),
        Column("valid_until", "Valid until", weight=1.2),
    ]
    if is_admin:
        columns.append(Column("owner", "Owner organisation", in_pdf=False))

    filters = _filters(
        ("Search", search_utils.clean_query(q)), ("Status", _label(status)),
        ("Type", {"initial": "First verification", "renewal": "Re-verification"}.get(application_type)),
        ("Instrument type", instrument_type), ("Issued", _range_text(date_from, date_to)),
    )
    report = _build("Certificates report", columns, rows, total, filters, current_user)
    return _deliver(report, format, "certificates", current_user, request)


# --- instruments ----------------------------------------------------------------------------------

@router.get("/instruments")
@limiter.limit(RATE_LIMIT_REPORTS)
def instruments_report(
    request: Request,
    format: Format = "csv",
    owner_id: Optional[str] = Query(default=None),
    q: search_utils.SearchText = None,
    type: search_utils.InstrumentTypeParam = None,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
    current_user: dict = Depends(get_current_user),
):
    """Instrument register, with each instrument's latest certificate and whether it is still valid.
    Owners and admins only, like GET /instruments."""
    docs = find_instruments(
        current_user, owner_id=owner_id, q=q, instrument_type=type, state_code=state_code, district_code=district_code,
    )
    docs.sort(key=lambda i: str(i.get("uiid", "")))
    total = len(docs)
    docs = docs[:REPORT_MAX_ROWS]

    # Latest certificate per instrument (the one with the furthest valid_until).
    latest: dict = {}
    for c in certificates_col.find({"instrument_id": {"$in": [d["_id"] for d in docs]}}, {"instrument_id": 1, "cert_no": 1, "valid_until": 1}):
        best = latest.get(c["instrument_id"])
        if best is None or rx._as_utc(c["valid_until"]) > rx._as_utc(best["valid_until"]):
            latest[c["instrument_id"]] = c

    is_admin = current_user["role"] == "admin"
    owners = _owner_orgs(d.get("owner_id") for d in docs) if is_admin else {}
    place = _place_lookup({((d.get("location") or {}).get("state_code"), (d.get("location") or {}).get("district_code")) for d in docs})

    now = datetime.now(timezone.utc)
    rows = []
    for d in docs:
        loc = d.get("location") or {}
        state, district = place(loc.get("state_code"), loc.get("district_code"))
        cert = latest.get(d["_id"])
        rows.append({
            "uiid": d.get("uiid", ""),
            "type": d.get("type", ""),
            "manufacturer": d.get("manufacturer", ""),
            "model": d.get("model", ""),
            "capacity": d.get("capacity", ""),
            "serial_no": d.get("serial_no", ""),
            "state": state,
            "district": district,
            "address": loc.get("address_line", ""),
            "cert_status": _cert_status(cert["valid_until"], now) if cert else "Not yet verified",
            "cert_no": (cert.get("cert_no") or cert["_id"]) if cert else "",
            "valid_until": rx.fmt_date(cert.get("valid_until")) if cert else "",
            "owner": owners.get(d.get("owner_id"), ""),
        })

    columns = [
        Column("uiid", "UIID", weight=1.2),
        Column("type", "Instrument type", weight=1.9),
        Column("manufacturer", "Manufacturer", weight=1.4),
        Column("model", "Model", weight=1.2),
        Column("capacity", "Capacity", weight=1.0),
        Column("serial_no", "Serial no.", weight=1.3),
        Column("state", "State", weight=1.3),
        Column("district", "District", weight=1.3),
        Column("address", "Address", in_pdf=False),
        Column("cert_status", "Certificate", weight=1.3),
        Column("cert_no", "Latest certificate no.", in_pdf=False),
        Column("valid_until", "Valid until", weight=1.2),
    ]
    if is_admin:
        columns.append(Column("owner", "Owner organisation", in_pdf=False))

    filters = _filters(
        ("Search", search_utils.clean_query(q)), ("Instrument type", type), ("State", state_code), ("District", district_code),
    )
    report = _build("Instrument register", columns, rows, total, filters, current_user)
    return _deliver(report, format, "instruments", current_user, request)


# --- audit log ------------------------------------------------------------------------------------

@router.get("/audit-logs")
@limiter.limit(RATE_LIMIT_REPORTS)
def audit_logs_report(
    request: Request,
    format: Format = "csv",
    event: Optional[str] = Query(None, max_length=64),
    outcome: Optional[Literal["success", "failure", "blocked", "ignored"]] = None,
    role: Optional[Literal["owner", "lmo", "gatc", "admin"]] = None,
    search: Optional[str] = Query(None, max_length=100),
    date_from: Optional[date] = Query(None, description="First day to include (UTC)"),
    date_to: Optional[date] = Query(None, description="Last day to include (UTC)"),
    current_user: dict = Depends(role_required("admin")),
):
    """Audit-trail report with the audit viewer's filters (dates are UTC days, as on that screen)."""
    query = admin_audit.build_query(event, outcome, role, search, date_from, date_to)
    collection = read_replica(audit_service.audit_logs_col)
    total = collection.count_documents(query)
    docs = list(collection.find(query).sort([("created_at", -1), ("_id", -1)]).limit(REPORT_MAX_ROWS))

    rows = [
        {
            "time": rx.fmt_datetime(d.get("created_at")),
            "event": _label(d.get("event")),
            "outcome": _label(d.get("outcome")),
            "email": d.get("email") or "",
            "role": d.get("role") or "",
            "actor": d.get("actor_email") or d.get("actor_id") or "",
            "ip": d.get("ip") or "",
            "detail": d.get("detail") or "",
        }
        for d in docs
    ]
    columns = [
        Column("time", "Time (IST)", weight=1.5),
        Column("event", "Event", weight=2.2),
        Column("outcome", "Outcome", weight=1.0),
        Column("email", "Account", weight=2.4),
        Column("role", "Role", weight=0.8),
        Column("actor", "Done by", weight=2.2),
        Column("ip", "IP address", weight=1.3),
        Column("detail", "Detail", weight=2.2),
    ]
    filters = _filters(
        ("Event", _label(event) if event else None), ("Outcome", _label(outcome)), ("Role", role),
        ("Email contains", (search or "").strip()),
        ("Dates (UTC)", _range_text(date_from, date_to)),
    )
    report = _build("Audit log report", columns, rows, total, filters, current_user)
    return _deliver(report, format, "audit-logs", current_user, request)
