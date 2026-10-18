"""CSV / PDF rendering (app/services/report_export.py). Pure: no database, no web framework."""
import csv
import io
from datetime import datetime, timezone

import pytest

from app.services import report_export as rx
from app.services.report_export import Column, Report

COLUMNS = [
    Column("cert_no", "Certificate no.", weight=2),
    Column("type", "Instrument type"),
    Column("note", "Note", in_pdf=False),
]


def _report(rows, **kw):
    return Report(
        title="Certificates report", columns=COLUMNS, rows=rows, generated_by="Asha (Admin)",
        generated_at=datetime(2026, 10, 17, 18, 30, tzinfo=timezone.utc), **kw,
    )


def _parse(data: bytes):
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def test_csv_has_bom_header_and_every_column_including_pdf_hidden_ones():
    data = rx.to_csv(_report([{"cert_no": "CERT-1", "type": "Platform Scale", "note": "ok"}]))
    assert data.startswith(b"\xef\xbb\xbf")  # Excel needs this to read UTF-8
    assert _parse(data) == [["Certificate no.", "Instrument type", "Note"], ["CERT-1", "Platform Scale", "ok"]]


def test_csv_quotes_commas_quotes_and_newlines():
    rows = [{"cert_no": 'A, "B"', "type": "line1\nline2", "note": None}]
    assert _parse(rx.to_csv(_report(rows)))[1] == ['A, "B"', "line1 line2", ""]


def test_csv_keeps_non_latin_text():
    rows = [{"cert_no": "C-1", "type": "तराजू", "note": "é"}]
    assert _parse(rx.to_csv(_report(rows)))[1][1:] == ["तराजू", "é"]


@pytest.mark.parametrize("text", ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "\tx", '=HYPERLINK("http://evil")'])
def test_csv_defuses_spreadsheet_formulas(text):
    row = _parse(rx.to_csv(_report([{"cert_no": text, "type": "x", "note": ""}])))[1]
    assert row[0] == "'" + text  # shown as plain text, never evaluated


def test_csv_leaves_ordinary_text_alone():
    assert rx.safe_cell("Acme - 2 (new)") == "Acme - 2 (new)"
    assert rx.safe_cell(None) == "" and rx.safe_cell(0) == "0"


def test_csv_with_no_rows_is_just_the_header():
    assert _parse(rx.to_csv(_report([]))) == [["Certificate no.", "Instrument type", "Note"]]


def test_pdf_is_a_valid_multipage_document():
    rows = [{"cert_no": f"CERT-{i}", "type": "Platform Scale"} for i in range(200)]
    pdf = rx.to_pdf(_report(rows, total=200))
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") > 1  # more than one page


def test_pdf_handles_empty_results_markup_and_unsupported_characters():
    assert rx.to_pdf(_report([])).startswith(b"%PDF-")
    nasty = [{"cert_no": "<b>x</b> & <para>", "type": "नमस्ते ₹ 😀"}]
    assert rx.to_pdf(_report(nasty, filters=[("Search", "a<b&c")])).startswith(b"%PDF-")


def test_pdf_text_escapes_markup_and_replaces_what_the_fonts_cannot_draw():
    assert rx.pdf_text("a<b & c") == "a&lt;b &amp; c"
    assert "नमस्ते" not in rx.pdf_text("नमस्ते") and "?" in rx.pdf_text("नमस्ते")
    assert rx.pdf_text(None) == ""


def test_truncated_flag():
    assert _report([{}] * 3, total=10).truncated is True
    assert _report([{}] * 3, total=3).truncated is False
    assert _report([{}] * 3).truncated is False


def test_dates_are_shown_in_india_time():
    # 20:00 UTC on the 17th is 01:30 on the 18th in India.
    assert rx.fmt_datetime(datetime(2026, 10, 17, 20, 0)) == "18 Oct 2026, 01:30"
    assert rx.fmt_datetime(datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)) == "18 Oct 2026, 01:30"
    assert rx.fmt_date(datetime(2026, 10, 17, 20, 0)) == "18 Oct 2026"
    assert rx.fmt_date("2026-10-17") == "17 Oct 2026"
    assert rx.fmt_datetime(None) == "" and rx.fmt_date(None) == ""


def test_render_picks_type_and_extension_and_rejects_unknown_formats():
    report = _report([{"cert_no": "C", "type": "T"}])
    assert rx.render(report, "csv")[1:] == ("text/csv; charset=utf-8", "csv")
    assert rx.render(report, "pdf")[1:] == ("application/pdf", "pdf")
    with pytest.raises(ValueError):
        rx.render(report, "xlsx")


def test_file_stem_uses_india_time():
    assert rx.file_stem("certificates", datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)) == "maapsetu-certificates-20261018-0130"
