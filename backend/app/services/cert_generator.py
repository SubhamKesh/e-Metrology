from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from io import BytesIO
from datetime import datetime, timedelta
import uuid

from app.config.db import (
    inspections_collection,
    applications_collection,
    instruments_collection,
    certificates_collection,
)
from app.services.qr_generator import generate_qr
from app.utils.upload_to_cloudinary import upload_bytes


def _generate_cert_number() -> str:
    return f"CERT-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def _generate_pdf_bytes(cert_no, instrument, inspection, valid_until) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 80, "Verification Certificate")

    c.setFont("Helvetica", 12)
    y = height - 140
    for line in [
        f"Certificate No: {cert_no}",
        f"Instrument: {instrument['type']} (Serial: {instrument['serial_no']})",
        f"Inspected on: {inspection['date']}",
        f"Result: {inspection['result']}",
        f"Valid Until: {valid_until.strftime('%d %b %Y')}",
    ]:
        c.drawString(80, y, line)
        y -= 25

    c.save()
    buf.seek(0)
    return buf.getvalue()


def issue_certificate(inspection_id: str) -> dict:
    """
    Called from app/services/status_transition.py when an inspection
    result is 'pass' and the application moves inspected -> certified.
    CONFIRM exact call site and function name with Deep.
    """
    inspection = inspections_collection.find_one({"_id": inspection_id})
    if not inspection:
        raise ValueError("Inspection not found")

    application = applications_collection.find_one({"_id": inspection["application_id"]})
    if not application:
        raise ValueError("Application not found for this inspection")

    instrument = instruments_collection.find_one({"_id": application["instrument_id"]})
    if not instrument:
        raise ValueError("Instrument not found for this application")

    cert_id = str(uuid.uuid4())
    cert_no = _generate_cert_number()
    valid_until = datetime.utcnow() + timedelta(days=365)

    qr_url = generate_qr(cert_id)
    pdf_bytes = _generate_pdf_bytes(cert_no, instrument, inspection, valid_until)
    pdf_url = upload_bytes(pdf_bytes, public_id=f"cert_{cert_id}", resource_type="raw")

    cert_doc = {
        "_id": cert_id,
        "inspection_id": inspection["_id"],
        "cert_no": cert_no,
        "qr_url": qr_url,
        "pdf_url": pdf_url,
        "issued_at": datetime.utcnow(),
        "valid_until": valid_until,
    }
    certificates_collection.insert_one(cert_doc)
    return cert_doc