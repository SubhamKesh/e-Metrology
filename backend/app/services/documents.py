"""Which documents an application needs, and whether the owner has uploaded them.

A fixed set of slots, one file each (uploading again replaces the file):
  * first verification: Tax invoice + Owner ID proof
  * re-verification:    Previous certificate (a fresh copy, uploaded after the last certificate was issued,
                        so an old upload cannot be reused for the next renewal)
The documents belong to the instrument. They are checked when the application is submitted
(routers/applications.py) and are locked while an application for the instrument is open.
"""
from datetime import datetime, timezone

from app.config.db import instrument_documents_col

SLOT_LABEL = {
    "tax_invoice": "Tax invoice",
    "owner_id_proof": "Owner ID proof",
    "previous_certificate": "Previous certificate",
}
SLOT_HINT = {
    "tax_invoice": "The purchase invoice for this instrument.",
    "owner_id_proof": "Aadhaar, PAN, voter ID, driving licence or passport of the owner.",
    "previous_certificate": "A copy of the certificate being renewed.",
}
INITIAL_SLOTS = ("tax_invoice", "owner_id_proof")
RENEWAL_SLOTS = ("previous_certificate",)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def required_slots(newest_certificate: dict | None) -> tuple[str, ...]:
    return RENEWAL_SLOTS if newest_certificate else INITIAL_SLOTS


def current_documents(instrument_oid, newest_certificate: dict | None) -> dict[str, dict]:
    """Slot -> stored document, leaving out a previous-certificate copy that is older than the newest
    certificate (it belongs to an earlier renewal)."""
    out = {d["slot"]: d for d in instrument_documents_col.find({"instrument_id": instrument_oid})}
    old = out.get("previous_certificate")
    issued = newest_certificate.get("issued_at") if newest_certificate else None
    if old and issued and _utc(old["uploaded_at"]) <= _utc(issued):
        del out["previous_certificate"]
    return out


def missing_required_documents(instrument_oid, newest_certificate: dict | None) -> list[str]:
    """Labels of the required documents that are still missing, in order. Empty means ready to submit."""
    have = current_documents(instrument_oid, newest_certificate)
    return [SLOT_LABEL[s] for s in required_slots(newest_certificate) if s not in have]
