from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId

from app.config.db import certificates_col, applications_col, instruments_col, users_col, inspections_col
from app.middleware.auth import get_current_user, role_required
from app.services.cert_generator import issue_certificate

router = APIRouter(prefix="/api/v1/certificates", tags=["certificates"])


def _serialize_cert(cert: dict) -> dict:
    valid_until = cert["valid_until"]
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    is_expired = valid_until < datetime.now(timezone.utc)

    return {
        "id": cert["_id"],
        "application_id": str(cert["application_id"]),
        "verified_on": cert["issued_at"].isoformat(),
        "valid_until": cert["valid_until"].isoformat(),
        "is_expired": is_expired,
        "qr_url": cert["qr_url"],
        "pdf_url": cert["pdf_url"],
    }


# IMPORTANT: this route must be registered BEFORE /{cert_id},
# otherwise FastAPI matches "verify" as a cert_id value.
@router.get("/verify/{cert_id}")
def verify_certificate(cert_id: str):
    """
    Public, unauthenticated. Powers verify-page/src/pages/[certId].jsx.

    Response shape below is the one confirmed with Aritra/Anushka's
    verify-page — this is the locked contract, not a proposal anymore.
    """
    cert = certificates_col.find_one({"_id": cert_id})
    if not cert:
        return {"valid": False, "reason": "not_found"}

    application = applications_col.find_one({"_id": cert["application_id"]})
    instrument = instruments_col.find_one({"_id": cert["instrument_id"]})
    owner = users_col.find_one({"_id": application["owner_id"]}) if application else None

    valid_until = cert["valid_until"]
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    is_expired = valid_until < datetime.now(timezone.utc)

    return {
        "valid": True,
        "certificate": {
            "id": cert["_id"],
            "verified_on": cert["issued_at"].isoformat(),
            "valid_until": cert["valid_until"].isoformat(),
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
            "location": instrument["location"] if instrument else None,
        },
    }


@router.get("/{cert_id}")
def get_certificate(cert_id: str, user=Depends(get_current_user)):
    cert = certificates_col.find_one({"_id": cert_id})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    return _serialize_cert(cert)


@router.get("/")
def list_certificates(user=Depends(get_current_user)):
    certs = list(certificates_col.find())
    return [_serialize_cert(c) for c in certs]


@router.post("/generate/{application_id}")
def generate_certificate(application_id: str, user=Depends(role_required("lmo", "gatc", "admin"))):
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
        raise HTTPException(status_code=502, detail=f"Certificate generation failed: {e}")

    return _serialize_cert(cert_doc)