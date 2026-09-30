from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from io import BytesIO
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from bson.binary import Binary
from pymongo.errors import DuplicateKeyError
import logging
import threading
import uuid
import qrcode

from app.config.db import (
    inspections_col,
    applications_col,
    instruments_col,
    certificates_col,
    users_col,
)
from app.utils.upload_to_cloudinary import upload_bytes
from app.utils.location_format import format_location
from app.services.owner_notifications import notify_certificate_issued
from app.config.settings import FRONTEND_VERIFY_URL

logger = logging.getLogger("maapsetu")

INK = (0.11, 0.15, 0.22)          # near-black navy for body text/borders
ACCENT = (0.05, 0.35, 0.25)       # deep green for the seal/header rule, evokes an official emblem
MUTED = (0.42, 0.45, 0.5)         # grey for field labels


def _generate_cert_number() -> str:
    return f"CERT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def _make_qr_png(verify_url: str) -> bytes:
    """QR code rendered in memory. It used to be uploaded to Cloudinary and then
    downloaded again just to be drawn into the PDF -- two network hops, either
    of which could sink the whole certificate. Now it never leaves the process."""
    img = qrcode.make(verify_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _safe_location(location) -> str | None:
    try:
        return format_location(location)
    except Exception:
        logger.warning("Could not format instrument location for certificate PDF.", exc_info=True)
        return None


def _draw_field_row(c, x, y, label, value, label_width=150):
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*MUTED)
    c.drawString(x, y, label)
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(*INK)
    c.drawString(x + label_width, y, str(value) if value else "-")


def _generate_pdf_bytes(cert_no, instrument, inspection, application, owner, valid_until, issued_at, qr_png, verify_url) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 20 * mm

    # Outer double border, the classic look of an official/govt-issued document
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(2.2)
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin)
    c.setLineWidth(0.6)
    c.rect(margin + 4 * mm, margin + 4 * mm, width - 2 * margin - 8 * mm, height - 2 * margin - 8 * mm)

    inner_left = margin + 14 * mm
    inner_right = width - margin - 14 * mm

    # Header block — emblem placeholder circle + authority name
    top = height - margin - 18 * mm
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(1.4)
    c.circle(width / 2, top + 6 * mm, 9 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(*ACCENT)
    c.drawCentredString(width / 2, top + 5 * mm, "LM")

    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(width / 2, top - 8 * mm, "GOVERNMENT OF INDIA")
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, top - 13 * mm, "DEPARTMENT OF LEGAL METROLOGY")

    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(1)
    c.line(inner_left, top - 18 * mm, inner_right, top - 18 * mm)

    c.setFont("Helvetica-Bold", 20)
    c.setFillColorRGB(*INK)
    c.drawCentredString(width / 2, top - 30 * mm, "CERTIFICATE OF VERIFICATION")
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(width / 2, top - 37 * mm, "Issued under the Legal Metrology Act")

    # Field block
    y = top - 55 * mm
    row_h = 9 * mm
    fields = [
        ("Certificate No.", cert_no),
        ("Instrument Type", instrument.get("type")),
        ("UIID", instrument.get("uiid")),
        ("Manufacturer", instrument.get("manufacturer")),
        ("Model", instrument.get("model")),
        ("Owner", owner.get("org_name") if owner else None),
        ("Location", _safe_location(instrument.get("location"))),
        ("Inspected On", inspection["inspected_at"].strftime("%d %b %Y") if hasattr(inspection["inspected_at"], "strftime") else inspection["inspected_at"]),
        ("Result", str(inspection.get("result", "")).upper()),
        ("Issued On", issued_at.strftime("%d %b %Y")),
        ("Valid Until", valid_until.strftime("%d %b %Y")),
    ]
    for label, value in fields:
        _draw_field_row(c, inner_left, y, label, value)
        y -= row_h

    # QR code, bottom-right of the field block, with a caption
    qr_size = 32 * mm
    qr_x = inner_right - qr_size
    qr_y = margin + 30 * mm
    try:
        c.drawImage(ImageReader(BytesIO(qr_png)), qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask="auto")
    except Exception:
        # Certificate is still valid without the QR rendering -- the printed
        # certificate number and the verify link both let anyone confirm it.
        logger.warning("Could not draw QR code on certificate PDF.", exc_info=True)
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 5 * mm, "Scan to verify authenticity")

    # Signature line, bottom-left, opposite the QR
    sig_x = inner_left
    sig_y = qr_y + 6 * mm
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.7)
    c.line(sig_x, sig_y, sig_x + 55 * mm, sig_y)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*MUTED)
    c.drawString(sig_x, sig_y - 5 * mm, "Legal Metrology Officer")
    c.drawString(sig_x, sig_y - 9.5 * mm, "Authorized Signatory")

    # Footer
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(width / 2, margin + 8 * mm, "This is a system-generated certificate and is valid without a physical signature.")
    c.drawCentredString(width / 2, margin + 4 * mm, f"Verify at: {verify_url}  |  Certificate No. {cert_no}")

    c.save()
    buf.seek(0)
    return buf.getvalue()


# One lock per application, so the inspection-time thread, the reconciler and a
# manual retry inside the same process can't issue two certificates at once.
_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(application_id) -> threading.Lock:
    key = str(application_id)
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def issue_certificate(inspection_id) -> dict:
    """
    Generates and stores a certificate for a passed inspection.

    Idempotent: one certificate per application, whoever calls (inspection
    route, background thread, RQ worker, reconciler, manual retry).

    Only the things a certificate can't exist without are allowed to fail it:
    the DB lookups and rendering the PDF. Cloudinary is best-effort -- if the
    PDF upload fails, the PDF is kept in MongoDB and served by the API instead
    (see routers/certificates.py), so a storage hiccup never leaves an owner
    with a 'certified' application and no certificate.
    """
    insp_oid = inspection_id if isinstance(inspection_id, ObjectId) else ObjectId(inspection_id)

    inspection = inspections_col.find_one({"_id": insp_oid})
    if not inspection:
        raise ValueError("Inspection not found")

    application = applications_col.find_one({"_id": inspection["application_id"]})
    if not application:
        raise ValueError("Application not found for this inspection")

    with _lock_for(application["_id"]):
        existing = certificates_col.find_one({"application_id": application["_id"]})
        if existing:
            return existing

        instrument = instruments_col.find_one({"_id": application["instrument_id"]})
        if not instrument:
            raise ValueError("Instrument not found for this application")

        owner = users_col.find_one({"_id": application["owner_id"]})

        cert_id = str(uuid.uuid4())
        cert_no = _generate_cert_number()
        issued_at = datetime.now(timezone.utc)
        valid_until = issued_at + timedelta(days=365)

        verify_url = f"{FRONTEND_VERIFY_URL.rstrip('/')}/{cert_id}"
        qr_png = _make_qr_png(verify_url)
        pdf_bytes = _generate_pdf_bytes(
            cert_no, instrument, inspection, application, owner, valid_until, issued_at, qr_png, verify_url
        )

        # Best-effort QR upload, kept only because older records/clients expose qr_url.
        qr_url = None
        try:
            qr_url = upload_bytes(qr_png, public_id=f"qr_{cert_id}", resource_type="image")
        except Exception:
            logger.warning("QR upload to Cloudinary failed for certificate %s (continuing).", cert_id, exc_info=True)

        # Cloudinary's raw delivery URL is derived from public_id verbatim, with
        # no automatic extension -- without ".pdf" the served file has no
        # extension and browsers open it as plain text.
        pdf_url = None
        try:
            pdf_url = upload_bytes(pdf_bytes, public_id=f"cert_{cert_id}.pdf", resource_type="raw")
        except Exception:
            logger.exception(
                "PDF upload to Cloudinary failed for certificate %s; storing the PDF in MongoDB instead. "
                "Check CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET.", cert_id,
            )

        cert_doc = {
            "_id": cert_id,
            "inspection_id": inspection["_id"],
            # Required by app/routers/dashboard.py's owner next_expiry lookup.
            "application_id": application["_id"],
            "instrument_id": instrument["_id"],
            "cert_no": cert_no,
            "qr_url": qr_url,
            "pdf_url": pdf_url,
            "issued_at": issued_at,
            "valid_until": valid_until,
        }
        if pdf_url is None:
            cert_doc["pdf_data"] = Binary(pdf_bytes)

        try:
            certificates_col.insert_one(cert_doc)
        except DuplicateKeyError:
            # Another process won the race (unique index on application_id).
            existing = certificates_col.find_one({"application_id": application["_id"]})
            if existing:
                return existing
            raise

    cert_doc.pop("pdf_data", None)
    # Email the owner their certificate (best-effort, never raises).
    notify_certificate_issued(cert_doc)
    return cert_doc
