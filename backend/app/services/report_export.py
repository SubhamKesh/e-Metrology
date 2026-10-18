"""Turns a table of rows into a CSV or PDF report.

Pure rendering: no database and no web framework in here, so it can be tested on its own.
The report endpoints (app/routers/reports.py) decide *which* rows a person may see; this module
only formats what it is given.

CSV  - UTF-8 with a byte-order mark so Excel opens Indian-language text correctly. Every cell that
       could be read as a spreadsheet formula is neutralised (see `safe_cell`).
PDF  - A4 landscape, a header with the report title, who made it, when and with which filters, a
       table whose header repeats on every page, and "Page x of y" in the footer. Text is limited to
       what the built-in PDF fonts can draw; anything else prints as "?" (the CSV keeps it intact).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

IST = timezone(timedelta(hours=5, minutes=30))

ORGANISATION = "Department of Legal Metrology"
PRODUCT = "MaapSetu"

# A spreadsheet treats a cell starting with one of these as a formula. Report data includes text that
# other people typed (manufacturer, address, ...), so such cells are prefixed with an apostrophe.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    # The PDF is a printable summary and fits fewer columns than the CSV, which carries everything.
    in_pdf: bool = True
    # Relative width of the column in the PDF.
    weight: float = 1.0


@dataclass
class Report:
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    # What the person asked for, as (label, value) pairs; printed on the PDF so the page explains itself.
    filters: list[tuple[str, str]] = field(default_factory=list)
    generated_by: str = ""
    generated_at: Optional[datetime] = None
    # How many rows matched in all; `rows` holds at most the export limit.
    total: Optional[int] = None

    @property
    def truncated(self) -> bool:
        return self.total is not None and self.total > len(self.rows)


# --- Formatting helpers ---------------------------------------------------------------------------

def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def fmt_datetime(value: Any) -> str:
    """'17 Oct 2026, 23:41' in India time; '' for nothing. MongoDB returns UTC without a tzinfo."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return _as_utc(value).astimezone(IST).strftime("%d %b %Y, %H:%M")
    return str(value)


def fmt_date(value: Any) -> str:
    """'17 Oct 2026' (India date) for a datetime or a YYYY-MM-DD string; '' for nothing."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return _as_utc(value).astimezone(IST).strftime("%d %b %Y")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value)


def safe_cell(value: Any) -> str:
    """Text for one CSV cell, with spreadsheet formulas defused."""
    if value is None:
        return ""
    text = str(value)
    # Line breaks inside a cell make the file hard to read and are never needed here.
    text = text.replace("\r\n", " ").replace("\n", " ")
    if text.startswith(_FORMULA_STARTS):
        text = "'" + text
    return text


def pdf_text(value: Any) -> str:
    """Text the built-in PDF fonts can draw, escaped for use inside a Paragraph."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    # The standard fonts cover Windows-1252. Other characters would print as black boxes.
    text = text.encode("cp1252", errors="replace").decode("cp1252")
    return escape(text)


def file_stem(kind: str, when: Optional[datetime] = None) -> str:
    """'maapsetu-applications-20261017-2341' (India time), used for the download's file name."""
    when = (when or datetime.now(timezone.utc)).astimezone(IST)
    return f"maapsetu-{kind}-{when.strftime('%Y%m%d-%H%M')}"


# --- CSV ------------------------------------------------------------------------------------------

def to_csv(report: Report) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([c.header for c in report.columns])
    for row in report.rows:
        writer.writerow([safe_cell(row.get(c.key)) for c in report.columns])
    return buf.getvalue().encode("utf-8-sig")


# --- PDF ------------------------------------------------------------------------------------------

_INK = colors.Color(0.11, 0.15, 0.22)
_ACCENT = colors.Color(0.05, 0.35, 0.25)
_MUTED = colors.Color(0.30, 0.34, 0.40)
_ZEBRA = colors.Color(0.95, 0.97, 0.96)
_RULE = colors.Color(0.80, 0.84, 0.82)


class _NumberedCanvas(canvas.Canvas):
    """Two-pass canvas: pages are kept until the end so the footer can say 'Page 2 of 5'."""

    def __init__(self, *args, footer_left: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages: list[dict] = []
        self._footer_left = footer_left

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        width, _ = self._pagesize
        self.saveState()
        self.setStrokeColor(_RULE)
        self.setLineWidth(0.5)
        self.line(12 * mm, 12 * mm, width - 12 * mm, 12 * mm)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(_MUTED)
        self.drawString(12 * mm, 8 * mm, self._footer_left)
        self.drawRightString(width - 12 * mm, 8 * mm, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def to_pdf(report: Report) -> bytes:
    pagesize = landscape(A4)
    left = right = 12 * mm
    usable = pagesize[0] - left - right

    generated_at = report.generated_at or datetime.now(timezone.utc)
    stamp = fmt_datetime(generated_at) + " IST"

    base = getSampleStyleSheet()
    brand = ParagraphStyle("brand", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5,
                           textColor=_ACCENT, leading=11)
    title = ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=17,
                           textColor=_INK, alignment=0, leading=21, spaceAfter=3)
    meta = ParagraphStyle("meta", parent=base["Normal"], fontName="Helvetica", fontSize=8.5,
                          textColor=_MUTED, leading=12)
    head = ParagraphStyle("head", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.5,
                          textColor=colors.white, leading=9.5)
    cell = ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.5,
                          textColor=_INK, leading=9.5)
    note = ParagraphStyle("note", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=8.5,
                          textColor=_MUTED, leading=12)

    cols = [c for c in report.columns if c.in_pdf] or list(report.columns)
    weight_sum = sum(c.weight for c in cols) or 1.0
    widths = [usable * c.weight / weight_sum for c in cols]

    story: list = [
        Paragraph(pdf_text(f"{PRODUCT}  |  {ORGANISATION}").upper(), brand),
        Paragraph(pdf_text(report.title), title),
    ]
    by = f" by {pdf_text(report.generated_by)}" if report.generated_by else ""
    story.append(Paragraph(f"Generated {pdf_text(stamp)}{by}", meta))
    if report.filters:
        applied = "; ".join(f"{pdf_text(k)}: {pdf_text(v)}" for k, v in report.filters)
        story.append(Paragraph(f"<b>Filters</b> - {applied}", meta))
    else:
        story.append(Paragraph("<b>Filters</b> - none (all records you may see)", meta))
    shown = len(report.rows)
    count = f"{shown} record{'s' if shown != 1 else ''}"
    if report.truncated:
        count = f"first {shown} of {report.total} records (the export limit; narrow the filters to see the rest)"
    story.append(Paragraph(f"<b>Records</b> - {count}", meta))
    story.append(Spacer(1, 4 * mm))

    if not report.rows:
        story.append(Paragraph("No records match these filters.", note))
    else:
        data = [[Paragraph(pdf_text(c.header), head) for c in cols]]
        for row in report.rows:
            data.append([Paragraph(pdf_text(row.get(c.key)) or "&nbsp;", cell) for c in cols])
        table = Table(data, colWidths=widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, _RULE),
        ]
        for i in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), _ZEBRA))
        table.setStyle(TableStyle(style))
        story.append(table)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize, leftMargin=left, rightMargin=right, topMargin=12 * mm, bottomMargin=17 * mm,
        title=report.title, author=ORGANISATION, subject=f"{PRODUCT} report",
    )
    footer = f"{PRODUCT} - {report.title} - {fmt_datetime(generated_at)} IST"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_left=pdf_text_plain(footer), **k))
    return buf.getvalue()


def pdf_text_plain(value: str) -> str:
    """Like pdf_text but for drawString (no markup escaping)."""
    return value.encode("cp1252", errors="replace").decode("cp1252")


def render(report: Report, fmt: str) -> tuple[bytes, str, str]:
    """(body, media type, file extension) for 'csv' or 'pdf'."""
    if fmt == "csv":
        return to_csv(report), "text/csv; charset=utf-8", "csv"
    if fmt == "pdf":
        return to_pdf(report), "application/pdf", "pdf"
    raise ValueError(f"Unsupported report format: {fmt}")
