from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
import logging
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId

from app.config.db import certificates_col, applications_col, instruments_col, users_col, inspections_col
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
        "valid_until": valid_until.isoformat(),
        "is_expired": is_expired,
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
        return not district or application.get("district_code") == district
    return False


# IMPORTANT: this route must be registered BEFORE /{cert_id},
# otherwise FastAPI matches "verify" as a cert_id value.
@router.get("/verify/{cert_id}")
def verify_certificate(cert_id: str):
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
    cache_key = f"cert-verify:{cert_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        if cached.get("valid") and cached.get("certificate"):
            # Entries cached before this fix hold naive timestamps; _as_utc makes
            # them comparable instead of raising TypeError (a 500 on every rescan).
            valid_until = _as_utc(datetime.fromisoformat(cached["certificate"]["valid_until"]))
            cached["certificate"]["valid_until"] = valid_until.isoformat()
            cached["certificate"]["is_expired"] = valid_until < datetime.now(timezone.utc)
        return cached

    cert = certificates_col.find_one({"_id": cert_id})
    if not cert:
        result = {"valid": False, "reason": "not_found"}
        # Short TTL — just enough to blunt someone hammering a bad/guessed
        # ID, without permanently caching a false negative if this ID is
        # about to exist (e.g. a request racing certificate issuance).
        cache_set(cache_key, result, ttl_seconds=60)
        return result

    application = applications_col.find_one({"_id": cert["application_id"]})
    instrument = instruments_col.find_one({"_id": cert["instrument_id"]})
    owner = users_col.find_one({"_id": application["owner_id"]}) if application else None

    valid_until = _as_utc(cert["valid_until"])
    issued_at = _as_utc(cert["issued_at"])
    is_expired = valid_until < datetime.now(timezone.utc)

    result = {
        "valid": True,
        "certificate": {
            "id": cert["_id"],
            "verified_on": issued_at.isoformat(),
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


@router.get("/")
def list_certificates(user=Depends(get_current_user)):
    """Certificates the caller is allowed to see, newest first: an owner's own,
    an officer's jurisdiction, everything for an admin. (This used to return
    every certificate in the database to any logged-in user.)"""
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
        else:
            app_filter = None  # no jurisdiction -> sees nothing
    else:
        app_filter = None

    if app_filter is None:
        return []

    # Self-heal: issue any certificate that failed to generate earlier. Runs in
    # the background (throttled) so this response is never delayed.
    start_reconcile(user["_id"] if role == "owner" else None)

    if app_filter:
        app_ids = [a["_id"] for a in applications_col.find(app_filter, {"_id": 1})]
        if not app_ids:
            return []
        cert_filter = {"application_id": {"$in": app_ids}}
    else:
        cert_filter = {}

    certs = list(certificates_col.find(cert_filter).sort("issued_at", -1))
    instrument_ids = list({c["instrument_id"] for c in certs if c.get("instrument_id")})
    instruments = {i["_id"]: i for i in instruments_col.find({"_id": {"$in": instrument_ids}})}
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