from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from app.config.db import certificates_col, applications_col, instruments_col, users_col
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/v1/certificates", tags=["certificates"])


def _serialize_cert(cert: dict) -> dict:
    return {
        "id": cert["_id"],
        "cert_no": cert["cert_no"],
        "qr_url": cert["qr_url"],
        "pdf_url": cert["pdf_url"],
        "issued_at": cert["issued_at"],
        "valid_until": cert["valid_until"],
    }


def _can_access(cert: dict, current_user: dict) -> bool:
    """
    owner  -> only certificates for their own applications
    lmo/gatc -> only certificates for applications assigned to them
    admin  -> everything
    """
    role = current_user["role"]
    if role == "admin":
        return True

    application = applications_col.find_one({"_id": cert["application_id"]})
    if not application:
        return False

    if role == "owner":
        return application["owner_id"] == current_user["_id"]
    if role in ("lmo", "gatc"):
        return application.get("assigned_officer_id") == current_user["_id"]
    return False


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
            "serial_no": instrument["serial_no"] if instrument else None,
        },
        "owner": {
            "org_name": owner["org_name"] if owner else None,
            "location": instrument["location"] if instrument else None,
        },
    }


@router.get("/{cert_id}")
def get_certificate(cert_id: str, current_user: dict = Depends(get_current_user)):
    cert = certificates_col.find_one({"_id": cert_id})
    if not cert:
        raise HTTPException(404, "Certificate not found")

    if not _can_access(cert, current_user):
        raise HTTPException(403, "Not authorized to view this certificate")

    return _serialize_cert(cert)


@router.get("/")
def list_certificates(current_user: dict = Depends(get_current_user)):
    role = current_user["role"]

    if role == "admin":
        certs = certificates_col.find()
    elif role == "owner":
        owner_app_ids = [
            a["_id"] for a in applications_col.find({"owner_id": current_user["_id"]}, {"_id": 1})
        ]
        certs = certificates_col.find({"application_id": {"$in": owner_app_ids}})
    elif role in ("lmo", "gatc"):
        officer_app_ids = [
            a["_id"]
            for a in applications_col.find({"assigned_officer_id": current_user["_id"]}, {"_id": 1})
        ]
        certs = certificates_col.find({"application_id": {"$in": officer_app_ids}})
    else:
        certs = []

    return [_serialize_cert(c) for c in certs]
