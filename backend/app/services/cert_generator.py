from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from xml.sax.saxutils import escape
from io import BytesIO
from pathlib import Path
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

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "maappramaan_logo.png"

INK = (0.11, 0.15, 0.22)          # near-black navy for body text/borders
ACCENT = (0.05, 0.35, 0.25)       # deep green for the seal/header rule, evokes an official emblem
MUTED = (0.30, 0.34, 0.40)        # slate grey for labels / secondary text
PAPER = (0.992, 0.988, 0.972)     # warm off-white, like security paper
LABEL_BG = (0.93, 0.96, 0.94)     # pale green tint for table label column


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


def _fmt_date(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%d %B %Y")
    return str(value) if value else "-"


def _draw_emblem(c, cx, cy, r):
    """Neutral circular seal (not a state emblem): concentric rings, a balance
    beam and pans -- a nod to weights & measures."""
    c.saveState()
    c.setStrokeColorRGB(*ACCENT)
    c.setFillColorRGB(*ACCENT)
    c.setLineWidth(1.6)
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.setLineWidth(0.5)
    c.circle(cx, cy, r - 1.6 * mm, stroke=1, fill=0)
    # balance
    c.setLineWidth(1)
    c.line(cx, cy - r * 0.50, cx, cy + r * 0.50)                       # pillar
    c.line(cx - r * 0.55, cy + r * 0.32, cx + r * 0.55, cy + r * 0.32)  # beam
    c.line(cx - r * 0.30, cy - r * 0.50, cx + r * 0.30, cy - r * 0.50)  # base
    for sx in (-1, 1):
        px = cx + sx * r * 0.55
        c.line(px, cy + r * 0.32, px - r * 0.2, cy - r * 0.02)
        c.line(px, cy + r * 0.32, px + r * 0.2, cy - r * 0.02)
        c.line(px - r * 0.2, cy - r * 0.02, px + r * 0.2, cy - r * 0.02)
    c.circle(cx, cy + r * 0.55, 0.9 * mm, stroke=0, fill=1)
    c.restoreState()


def _double_rule(c, x1, x2, y):
    c.saveState()
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(1.2)
    c.line(x1, y, x2, y)
    c.setLineWidth(0.4)
    c.line(x1, y - 1.2 * mm, x2, y - 1.2 * mm)
    c.restoreState()


def _generate_pdf_bytes(cert_no, instrument, inspection, application, owner, valid_until, issued_at, qr_png, verify_url) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Certificate of Verification - {cert_no}")
    c.setAuthor("Department of Legal Metrology")
    c.setSubject("Certificate of Verification (digitally generated)")
    width, height = A4

    outer = 10 * mm
    inner = outer + 3 * mm
    pad = 10 * mm                              # border -> content gap
    left = inner + pad
    right = width - inner - pad
    content_w = right - left
    cx = width / 2

    # ---- Page furniture: paper tint, double border, corner ornaments ------
    c.setFillColorRGB(*PAPER)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(2.4)
    c.rect(outer, outer, width - 2 * outer, height - 2 * outer)
    c.setLineWidth(0.6)
    c.rect(inner, inner, width - 2 * inner, height - 2 * inner)
    c.setFillColorRGB(*ACCENT)
    for ox, oy in ((inner, inner), (width - inner, inner), (inner, height - inner), (width - inner, height - inner)):
        c.circle(ox, oy, 1.4 * mm, stroke=0, fill=1)

    # ---- Header -------------------------------------------------------------
    y = height - inner - 9 * mm
    c.setFont("Times-Roman", 8.5)
    c.setFillColorRGB(*MUTED)
    c.drawString(left, y, f"Certificate No.: {cert_no}")
    c.drawRightString(right, y, f"Date of Issue: {_fmt_date(issued_at)}")

    logo_size = 23 * mm
    try:
        c.drawImage(ImageReader(str(LOGO_PATH)), cx - logo_size / 2, y - 2 * mm - logo_size,
                    width=logo_size, height=logo_size, mask="auto")
    except Exception:
        # Missing/unreadable logo file must never block certificate issuance.
        logger.warning("Could not draw logo on certificate PDF; using plain seal.", exc_info=True)
        _draw_emblem(c, cx, y - 12 * mm, 8.5 * mm)

    y -= 32 * mm
    c.setFillColorRGB(*ACCENT)
    c.setFont("Times-Bold", 13)
    c.drawCentredString(cx, y, "GOVERNMENT OF INDIA")
    y -= 6.2 * mm
    ministry = "MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION"
    # Shrink-to-fit so the long ministry name always stays inside the margins.
    ministry_size = 15
    while ministry_size > 9 and stringWidth(ministry, "Times-Bold", ministry_size) > content_w:
        ministry_size -= 0.25
    c.setFont("Times-Bold", ministry_size)
    c.drawCentredString(cx, y, ministry)
    y -= 4 * mm
    _double_rule(c, left, right, y)

    y -= 11 * mm
    c.setFillColorRGB(*INK)
    c.setFont("Times-Bold", 23)
    c.drawCentredString(cx, y, "CERTIFICATE OF VERIFICATION")
    y -= 6.5 * mm
    c.setFont("Times-Italic", 10.5)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString(cx, y, "Issued under the Legal Metrology Act")

    # ---- Preamble (wrapped, never leaves the margins) ----------------------
    result = str(inspection.get("result", "") or "").upper() or "-"
    body = ParagraphStyle("body", fontName="Times-Roman", fontSize=10.5, leading=15.5,
                          alignment=TA_JUSTIFY, textColor=Color(*INK))
    preamble = Paragraph(
        "This is to certify that the weighing / measuring instrument described below has been "
        "duly inspected and verified by the undersigned authority in accordance with the "
        f"provisions of the Legal Metrology Act and the rules made thereunder, and the result of "
        f"verification is recorded as <b>{escape(result)}</b>.",
        body,
    )
    y -= 5 * mm
    _, ph = preamble.wrap(content_w, 1000)
    preamble.drawOn(c, left, y - ph)
    y -= ph + 5 * mm

    # ---- Details table ------------------------------------------------------
    label_st = ParagraphStyle("lbl", fontName="Times-Bold", fontSize=9.5, leading=12, textColor=Color(*MUTED))
    value_st = ParagraphStyle("val", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5, textColor=Color(*INK))

    def cell(v):
        return Paragraph(escape(str(v)) if v else "-", value_st)

    rows = [
        ("Certificate No.", cert_no),
        ("Instrument Type", instrument.get("type")),
        ("Unique Instrument ID (UIID)", instrument.get("uiid")),
        ("Manufacturer", instrument.get("manufacturer")),
        ("Model", instrument.get("model")),
        ("Owner / Organisation", owner.get("org_name") if owner else None),
        ("Location of Instrument", _safe_location(instrument.get("location"))),
        ("Date of Inspection", _fmt_date(inspection.get("inspected_at"))),
        ("Result of Verification", result),
        ("Date of Issue", _fmt_date(issued_at)),
        ("Valid Until", _fmt_date(valid_until)),
    ]
    data = [[Paragraph(escape(l).upper(), label_st), cell(v)] for l, v in rows]
    table = Table(data, colWidths=[content_w * 0.34, content_w * 0.66])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, -1), Color(*LABEL_BG)),
        ("GRID", (0, 0), (-1, -1), 0.5, Color(*ACCENT)),
        ("BOX", (0, 0), (-1, -1), 1.1, Color(*ACCENT)),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
    ]))
    _, th = table.wrap(content_w, 1000)
    table.drawOn(c, left, y - th)
    y -= th + 5 * mm

    # ---- Validity note ------------------------------------------------------
    note_st = ParagraphStyle("note", fontName="Times-Italic", fontSize=9.5, leading=13,
                             alignment=TA_CENTER, textColor=Color(*MUTED))
    note = Paragraph(
        f"This certificate is valid until <b>{escape(_fmt_date(valid_until))}</b> unless the "
        "instrument is repaired, altered or tampered with, or the certificate is suspended or cancelled.",
        note_st,
    )
    _, nh = note.wrap(content_w, 1000)
    note.drawOn(c, left, y - nh)

    # ---- Bottom block: QR | seal text | signature ---------------------------
    base = inner + 21 * mm                     # leaves room for the footer
    qr_size = 32 * mm
    try:
        c.setFillColorRGB(1, 1, 1)
        c.setStrokeColorRGB(*ACCENT)
        c.setLineWidth(0.8)
        c.rect(left, base, qr_size + 4 * mm, qr_size + 4 * mm, stroke=1, fill=1)
        c.drawImage(ImageReader(BytesIO(qr_png)), left + 2 * mm, base + 2 * mm,
                    width=qr_size, height=qr_size, preserveAspectRatio=True, mask="auto")
    except Exception:
        # Certificate is still valid without the QR rendering -- the printed
        # certificate number and the verify link both let anyone confirm it.
        logger.warning("Could not draw QR code on certificate PDF.", exc_info=True)
    cap = ParagraphStyle("cap", fontName="Times-Roman", fontSize=8, leading=10.5, textColor=Color(*MUTED))
    capp = Paragraph("Scan the QR code to verify the authenticity of this certificate online.", cap)
    cap_w = 52 * mm
    _, cap_h = capp.wrap(cap_w, 100)
    capp.drawOn(c, left + qr_size + 4 * mm + 5 * mm, base + (qr_size + 4 * mm) / 2 - cap_h / 2)

    # Signature block (right)
    sig_w = 62 * mm
    sig_x2 = right
    sig_x1 = sig_x2 - sig_w
    sig_line_y = base + 17 * mm
    c.setFont("Times-Italic", 8.5)
    c.setFillColorRGB(*ACCENT)
    c.drawCentredString((sig_x1 + sig_x2) / 2, sig_line_y + 11 * mm, "Digitally generated & electronically issued")
    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString((sig_x1 + sig_x2) / 2, sig_line_y + 6.5 * mm, f"Date: {_fmt_date(issued_at)}")
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.7)
    c.line(sig_x1, sig_line_y, sig_x2, sig_line_y)
    c.setFont("Times-Bold", 10)
    c.setFillColorRGB(*INK)
    c.drawCentredString((sig_x1 + sig_x2) / 2, sig_line_y - 5 * mm, "Legal Metrology Officer")
    c.setFont("Times-Roman", 9)
    c.setFillColorRGB(*MUTED)
    c.drawCentredString((sig_x1 + sig_x2) / 2, sig_line_y - 9.5 * mm, "Authorised Signatory")
    c.drawCentredString((sig_x1 + sig_x2) / 2, sig_line_y - 14 * mm, "Department of Legal Metrology")

    # ---- Footer -------------------------------------------------------------
    fy = inner + 12 * mm
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(0.5)
    c.line(left, fy + 5 * mm, right, fy + 5 * mm)
    foot = ParagraphStyle("foot", fontName="Times-Italic", fontSize=8, leading=10.5,
                          alignment=TA_CENTER, textColor=Color(*MUTED))
    fp = Paragraph(
        "This is a system-generated certificate and is valid without a physical signature or seal.<br/>"
        f"Verify with Certificate ID <b>{escape(cert_no)}</b> on the MaapSetu app.",
        foot,
    )
    _, fh = fp.wrap(content_w, 100)
    fp.drawOn(c, left, fy + 3 * mm - fh)

    c.showPage()
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
