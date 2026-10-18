from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
import logging
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from bson.errors import InvalidId

from app.config.settings import REVERIFY_WINDOW_DAYS, EXPIRY_REMINDER_DAYS
from app.models.instrument import ALLOWED_INSTRUMENT_TYPES
from app.utils import search as search_utils
from app.config.db import certificates_col, applications_col, instruments_col, users_col, inspections_col, read_replica
from app.utils.location_format import format_location
from app.utils.cache import cache_get, cache_set
from app.middleware.auth import get_current_user, role_required
from app.services.cert_generator import issue_certificate
from app.services.jobs import (
    find_applications_missing_certificate,
    record_certificate_failure,
    start_reconcile,
)

logger = logging.getLogger("maapsetu")

router = APIRouter(prefix="/api/v1/certificates", tags=["certificates"])


def _as_utc(dt: datetime) -> datetime:
    # Mongo hands datetimes back naive (UTC). Serialize them with an explicit
    # offset, otherwise the browser parses "2027-01-01T10:00:00" as local time.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _serialize_cert(cert: dict, instrument: dict | None = None) -> dict:
    valid_until = _as_utc(cert["valid_until"])
    issued_at = _as_utc(cert["issued_at"])
    is_expired = valid_until < datetime.now(timezone.utc)

    return {
        "id": cert["_id"],
        "cert_no": cert.get("cert_no"),
        "application_id": str(cert["application_id"]),
        "instrument_id": str(cert["instrument_id"]) if cert.get("instrument_id") else None,
        "application_type": cert.get("application_type") or "initial",
        "previous_certificate_id": cert.get("previous_certificate_id"),
        "previous_cert_no": cert.get("previous_cert_no"),
        "seal_number": cert.get("seal_number"),
        "instrument": (
            {
                "type": instrument.get("type"),
                "uiid": instrument.get("uiid"),
                "manufacturer": instrument.get("manufacturer"),
                "model": instrument.get("model"),
                "location": _safe_location(instrument),
            }
            if instrument
            else None
        ),
        "verified_on": issued_at.isoformat(),
        "valid_from": _as_utc(cert.get("valid_from") or cert["issued_at"]).isoformat(),
        "valid_until": valid_until.isoformat(),
        "is_expired": is_expired,
        # From this moment the owner may apply for re-verification.
        "renewal_opens_on": (valid_until - timedelta(days=REVERIFY_WINDOW_DAYS)).isoformat(),
        "qr_url": cert.get("qr_url"),
        "pdf_url": cert.get("pdf_url"),
        # True when the PDF is held by the API itself (Cloudinary upload failed);
        # the client then downloads it from GET /certificates/{id}/pdf.
        "has_pdf": bool(cert.get("pdf_url") or cert.get("pdf_data")),
    }


def _safe_location(instrument: dict):
    try:
        return format_location(instrument.get("location"))
    except Exception:
        return None


def _can_view_cert(user: dict, cert: dict) -> bool:
    """Owners see their own certificates, officers those inside their
    jurisdiction, admins everything. Fails closed."""
    role = user.get("role")
    if role == "admin":
        return True
    application = applications_col.find_one({"_id": cert["application_id"]}, {"owner_id": 1, "state_code": 1, "district_code": 1})
    if not application:
        return False
    if role == "owner":
        return application.get("owner_id") == user["_id"]
    if role in ("lmo", "gatc"):
        jurisdiction = user.get("jurisdiction")
        if not jurisdiction or not jurisdiction.get("state_code"):
            return False  # no jurisdiction on file -> nothing
        if application.get("state_code") != jurisdiction["state_code"]:
            return False
        district = jurisdiction.get("district_code")
        if not district:
            return role == "gatc"  # only GATC is state-wide; an LMO without a district sees nothing
        return application.get("district_code") == district
    return False


# IMPORTANT: this route must be registered BEFORE /{cert_id},
# otherwise FastAPI matches "verify" as a cert_id value.
@router.get("/verify/{cert_id}")
def verify_certificate(cert_id: str):
    """Public verification result. Adds a live `reverification` block for an expired
    certificate whose instrument has an application in progress, so a shopkeeper who
    has applied sees "re-verification in progress" instead of a bare "expired".
    That block is never cached; the rest is (see _verify_payload)."""
    result = dict(_verify_payload(cert_id))
    instrument_id = result.pop("_instrument_id", None)
    cert = result.get("certificate")
    if result.get("valid") and cert and cert.get("is_expired") and instrument_id:
        try:
            open_app = read_replica(applications_col).find_one(
                {"instrument_id": ObjectId(instrument_id), "status": {"$in": ["submitted", "scheduled", "inspected"]}},
                sort=[("submitted_at", -1)],
            )
        except InvalidId:
            open_app = None
        if open_app:
            result["reverification"] = {
                "in_progress": True,
                "status": open_app["status"],
                "applied_on": _as_utc(open_app["submitted_at"]).isoformat(),
            }
    return result


def _verify_payload(cert_id: str):
    """
    Public, unauthenticated. Powers verify-page/src/pages/[certId].jsx.

    Response shape below is the one confirmed with Aritra/Anushka's
    verify-page — this is the locked contract, not a proposal anymore.

    Cached (see app/utils/cache.py) — this is a public, unauthenticated,
    QR-code-driven endpoint that can get hit far more often than any
    authenticated route, and a certificate's underlying data essentially
    never changes once issued. `is_expired` is the one field that's
    genuinely time-sensitive, so it's recomputed fresh on every call, cache
    hit or not, rather than trusting whatever value happened to be cached.
    """
    # Accept either the internal certificate id (what the QR code carries) or
    # the human-readable certificate number printed on the PDF (CERT-YYYYMMDD-XXXXXX).
    cert_id = cert_id.strip()
    cache_key = f"cert-verify:{cert_id.upper()}"
    cached = cache_get(cache_key)
    if cached is not None:
        if cached.get("valid") and cached.get("certificate"):
            # Entries cached before this fix hold naive timestamps; _as_utc makes
            # them comparable instead of raising TypeError (a 500 on every rescan).
            valid_until = _as_utc(datetime.fromisoformat(cached["certificate"]["valid_until"]))
            cached["certificate"]["valid_until"] = valid_until.isoformat()
            cached["certificate"]["is_expired"] = valid_until < datetime.now(timezone.utc)
        return cached

    certs = read_replica(certificates_col)
    cert = certs.find_one({"_id": cert_id}) or certs.find_one({"cert_no": cert_id.upper()})
    if not cert:
        result = {"valid": False, "reason": "not_found"}
        # Short TTL — just enough to blunt someone hammering a bad/guessed
        # ID, without permanently caching a false negative if this ID is
        # about to exist (e.g. a request racing certificate issuance).
        cache_set(cache_key, result, ttl_seconds=60)
        return result

    application = read_replica(applications_col).find_one({"_id": cert["application_id"]})
    instrument = read_replica(instruments_col).find_one({"_id": cert["instrument_id"]})
    owner = read_replica(users_col).find_one({"_id": application["owner_id"]}) if application else None

    valid_until = _as_utc(cert["valid_until"])
    issued_at = _as_utc(cert["issued_at"])
    is_expired = valid_until < datetime.now(timezone.utc)

    result = {
        "valid": True,
        # Internal: lets verify_certificate() look up an in-progress re-verification. Never sent to the client.
        "_instrument_id": str(cert["instrument_id"]) if cert.get("instrument_id") else None,
        "certificate": {
            "id": cert["_id"],
            "cert_no": cert.get("cert_no"),
            # Printed on the seal: lets anyone check the seal on the instrument against the record.
            "seal_number": cert.get("seal_number"),
            "verified_on": issued_at.isoformat(),
            "valid_from": _as_utc(cert.get("valid_from") or cert["issued_at"]).isoformat(),
            "valid_until": valid_until.isoformat(),
            "is_expired": is_expired,
        },
        "instrument": {
            "type": instrument["type"] if instrument else None,
            "manufacturer": instrument["manufacturer"] if instrument else None,
            "model": instrument["model"] if instrument else None,
            "uiid": instrument["uiid"] if instrument else None,
        },
        "owner": {
            "org_name": owner["org_name"] if owner else None,
            "location": format_location(instrument["location"]) if instrument else None,
        },
    }
    cache_set(cache_key, result, ttl_seconds=300)
    return result


@router.get("/pending")
def list_pending_certificates(user=Depends(get_current_user)):
    """Applications that are certified but whose certificate document does not
    exist yet (still generating, or generation failed). Lets the owner UI say
    "your certificate is being prepared" instead of showing an empty list.
    Also nudges the background reconciler."""
    role = user.get("role")
    if role == "owner":
        owner_filter = user["_id"]
    elif role == "admin":
        owner_filter = None
    else:
        return []
    start_reconcile(owner_filter)
    # grace_seconds=0: show everything that is certified but has no certificate.
    missing = find_applications_missing_certificate(owner_filter, grace_seconds=0)
    instruments = {
        i["_id"]: i
        for i in instruments_col.find({"_id": {"$in": [a["instrument_id"] for a in missing]}})
    }
    return [
        {
            "application_id": str(a["_id"]),
            "instrument": (
                {"type": instruments[a["instrument_id"]].get("type"), "uiid": instruments[a["instrument_id"]].get("uiid")}
                if a["instrument_id"] in instruments
                else None
            ),
            "failed": bool(a.get("certificate_error")),
        }
        for a in missing
    ]


@router.get("/{cert_id}/pdf")
def download_certificate_pdf(cert_id: str, user=Depends(get_current_user)):
    cert = certificates_col.find_one({"_id": cert_id})
    if not cert or not _can_view_cert(user, cert):
        raise HTTPException(404, "Certificate not found")
    data = cert.get("pdf_data")
    if data:
        return Response(
            content=bytes(data),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{cert.get("cert_no") or cert_id}.pdf"'},
        )
    if cert.get("pdf_url"):
        return RedirectResponse(cert["pdf_url"])
    raise HTTPException(404, "PDF not available for this certificate")


@router.get("/{cert_id}")
def get_certificate(cert_id: str, user=Depends(get_current_user)):
    cert = certificates_col.find_one({"_id": cert_id})
    # 404 (not 403) for someone else's certificate so ids can't be probed.
    if not cert or not _can_view_cert(user, cert):
        raise HTTPException(404, "Certificate not found")
    instrument = instruments_col.find_one({"_id": cert.get("instrument_id")})
    return _serialize_cert(cert, instrument)


def find_certificates(
    user: dict,
    q: Optional[str] = None,
    status: Optional[str] = None,
    application_type: Optional[str] = None,
    instrument_type: Optional[str] = None,
    date_from=None,
    date_to=None,
) -> tuple[list[dict], dict]:
    """(certificates, instruments by id) the caller may see, newest first, narrowed by the optional
    search filters. Shared by GET /certificates and the report export.

    Who may see what is decided first (an owner's own, an officer's jurisdiction, everything for an
    admin) and no filter can widen it."""
    role = user.get("role")
    if role == "admin":
        app_filter: dict | None = {}
    elif role == "owner":
        app_filter = {"owner_id": user["_id"]}
    elif role in ("lmo", "gatc"):
        jurisdiction = user.get("jurisdiction")
        if jurisdiction and jurisdiction.get("state_code"):
            app_filter = {"state_code": jurisdiction["state_code"]}
            if jurisdiction.get("district_code"):
                app_filter["district_code"] = jurisdiction["district_code"]
            elif role == "lmo":
                app_filter = None  # LMO is district-level; no district -> nothing
        else:
            app_filter = None  # no jurisdiction -> sees nothing
    else:
        app_filter = None

    if app_filter is None:
        return [], {}

    if app_filter:
        app_ids = [a["_id"] for a in applications_col.find(app_filter, {"_id": 1})]
        if not app_ids:
            return [], {}
        scope: dict = {"application_id": {"$in": app_ids}}
    else:
        scope = {}

    extra: list[dict] = []
    text = search_utils.clean_query(q)
    search_utils.check_instrument_type(instrument_type, ALLOWED_INSTRUMENT_TYPES)
    now = search_utils.now_utc_naive()
    if status == "valid":
        extra.append({"valid_until": {"$gte": now}})
    elif status == "expired":
        extra.append({"valid_until": {"$lt": now}})
    elif status == "expiring":
        # Still valid but inside the first expiry-reminder window (30 days by default).
        extra.append({"valid_until": {"$gte": now, "$lt": now + timedelta(days=max(EXPIRY_REMINDER_DAYS))}})
    if application_type:
        extra.append({"application_type": "renewal"} if application_type == "renewal"
                     else {"application_type": {"$ne": "renewal"}})
    window = search_utils.ist_window(date_from, date_to)
    if window:
        extra.append({"issued_at": window})
    inst_filter = search_utils.instrument_filter(None, instrument_type)
    if inst_filter:
        ids = [i["_id"] for i in instruments_col.find(inst_filter, {"_id": 1}).limit(search_utils.MAX_INSTRUMENT_MATCHES)]
        extra.append({"instrument_id": {"$in": ids}})
    if text:
        pattern = search_utils.contains(text)
        or_clauses: list[dict] = [
            {"_id": text}, {"cert_no": pattern}, {"seal_number": pattern}, {"previous_cert_no": pattern},
        ]
        text_filter = search_utils.instrument_filter(text)
        ids = [i["_id"] for i in instruments_col.find(text_filter, {"_id": 1}).limit(search_utils.MAX_INSTRUMENT_MATCHES)]
        if ids:
            or_clauses.append({"instrument_id": {"$in": ids}})
        extra.append({"$or": or_clauses})

    certs = list(certificates_col.find(search_utils.combine(scope, extra)).sort("issued_at", -1))
    instrument_ids = list({c["instrument_id"] for c in certs if c.get("instrument_id")})
    instruments = {i["_id"]: i for i in instruments_col.find({"_id": {"$in": instrument_ids}})}
    return certs, instruments


@router.get("/")
def list_certificates(
    q: search_utils.SearchText = None,
    status: Annotated[Optional[Literal["valid", "expiring", "expired"]], Query(description="Validity right now")] = None,
    application_type: Annotated[Optional[Literal["initial", "renewal"]], Query()] = None,
    instrument_type: search_utils.InstrumentTypeParam = None,
    date_from: search_utils.DateFrom = None,
    date_to: search_utils.DateTo = None,
    user=Depends(get_current_user),
):
    """Certificates the caller is allowed to see, newest first: an owner's own,
    an officer's jurisdiction, everything for an admin. (This used to return
    every certificate in the database to any logged-in user.)

    Optional search filters, combined with AND: `q` matches the certificate number, seal number,
    the number it renews, its id, or the instrument's UIID / serial number / manufacturer / model /
    type; `status` is validity right now (`expiring` = valid but within the first expiry-reminder
    window); the dates are India calendar days of issue."""
    if user.get("role") in ("owner", "admin", "lmo", "gatc"):
        # Self-heal: issue any certificate that failed to generate earlier. Runs in
        # the background (throttled) so this response is never delayed.
        start_reconcile(user["_id"] if user.get("role") == "owner" else None)
    certs, instruments = find_certificates(
        user, q=q, status=status, application_type=application_type, instrument_type=instrument_type,
        date_from=date_from, date_to=date_to,
    )
    return [_serialize_cert(c, instruments.get(c.get("instrument_id"))) for c in certs]


@router.post("/generate/{application_id}")
def generate_certificate(application_id: str, user=Depends(role_required("lmo", "gatc", "admin", "owner"))):
    """
    Manually (re-)issues a certificate for an application, e.g. to retry
    after cert generation failed at inspection time (see the try/except
    around issue_certificate() in routers/inspections.py).

    Deliberately does NOT accept certificate data in the request body —
    everything is looked up from the DB (application -> instrument -> most
    recent passing inspection) so a caller can't fabricate a certificate
    for arbitrary data. This replaces an earlier draft endpoint that took
    owner/instrument/etc. straight from the request payload; that version
    was never wired to save anything to certificates_col, so certs it
    "generated" wouldn't show up anywhere else in the app (dashboard,
    /verify/{cert_id}, etc.).
    """
    try:
        app_oid = ObjectId(application_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid application_id")

    application = applications_col.find_one({"_id": app_oid})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Owners may retry generation for their own applications only.
    if user.get("role") == "owner" and application.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=404, detail="Application not found")

    if application["status"] != "certified":
        raise HTTPException(
            status_code=409,
            detail=f"Application must be 'certified' to issue a certificate (currently '{application['status']}')",
        )

    existing = certificates_col.find_one({"application_id": app_oid})
    if existing:
        return _serialize_cert(existing)

    inspection = inspections_col.find_one(
        {"application_id": app_oid, "result": "pass"},
        sort=[("inspected_at", -1)],
    )
    if not inspection:
        raise HTTPException(status_code=404, detail="No passing inspection found for this application")

    try:
        cert_doc = issue_certificate(inspection["_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Manual certificate generation failed for application %s", application_id)
        try:
            record_certificate_failure(app_oid, f"{type(e).__name__}: {e}")
        except Exception:
            pass
        detail = "Certificate generation failed. Please try again shortly."
        if user.get("role") != "owner":
            detail = f"Certificate generation failed: {e}"
        raise HTTPException(status_code=502, detail=detail)

    applications_col.update_one({"_id": app_oid}, {"$unset": {"certificate_error": "", "certificate_error_at": ""}})
    return _serialize_cert(cert_doc)