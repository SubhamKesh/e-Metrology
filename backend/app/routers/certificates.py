from fastapi import APIRouter, Depends, HTTPException
from app.config.db import certificates_collection, inspections_collection, applications_collection, instruments_collection
from app.middleware.auth import get_current_user
from datetime import datetime

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


# IMPORTANT: this route must be registered BEFORE /{cert_id},
# otherwise FastAPI matches "verify" as a cert_id value.
@router.get("/verify/{cert_id}")
def verify_certificate(cert_id: str):
    cert = certificates_collection.find_one({"_id": cert_id})
    if not cert:
        return {"valid": False}

    inspection = inspections_collection.find_one({"_id": cert["inspection_id"]})
    application = applications_collection.find_one({"_id": inspection["application_id"]})
    instrument = instruments_collection.find_one({"_id": application["instrument_id"]})

    return {
        "valid": cert["valid_until"] > datetime.utcnow(),
        "cert_no": cert["cert_no"],
        "instrument_type": instrument["type"],
        "serial_no": instrument["serial_no"],
        "valid_until": cert["valid_until"],
    }


@router.get("/{cert_id}")
def get_certificate(cert_id: str, user=Depends(get_current_user)):
    cert = certificates_collection.find_one({"_id": cert_id})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    return _serialize_cert(cert)


@router.get("/")
def list_certificates(user=Depends(get_current_user)):
    certs = list(certificates_collection.find())
    return [_serialize_cert(c) for c in certs]