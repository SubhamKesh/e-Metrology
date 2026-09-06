from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from app.config.db import certificates_col, applications_col, instruments_col, users_col
from app.middleware.auth import get_current_user

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
