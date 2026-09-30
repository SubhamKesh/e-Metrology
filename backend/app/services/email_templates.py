"""
Email content for the owner status-update mails (see owner_notifications.py).

Pure functions: context in, (subject, plain_text, html) out. No DB, no SMTP,
so every template is trivially unit-testable.

Everything that ends up inside the HTML goes through html.escape() -- values
like manufacturer, model and the officer's inspection observations are typed
by users, so they must never be dropped into markup raw.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Optional

BRAND = "MaapSetu"

_TONES = {
    "info": "#1d4ed8",
    "success": "#047857",
    "warning": "#b45309",
    "danger": "#b91c1c",
}


def _fmt_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    return str(value) if value else "-"


def _instrument_rows(inst: dict) -> list[tuple[str, str]]:
    make_model = " ".join(p for p in (inst.get("manufacturer"), inst.get("model")) if p)
    rows = [
        ("Instrument", inst.get("type") or "-"),
        ("UIID", inst.get("uiid") or "-"),
        ("Make / model", make_model or "-"),
        ("Serial no.", inst.get("serial_no") or "-"),
    ]
    if inst.get("location"):
        rows.append(("Location", inst["location"]))
    return rows


def _build(
    *,
    subject: str,
    owner_name: str,
    heading: str,
    paragraphs: list[str],
    rows: list[tuple[str, str]],
    tone: str = "info",
    cta: Optional[tuple[str, str]] = None,
    closing: Optional[str] = None,
) -> tuple[str, str, str]:
    # ---- plain text ----
    text_lines = [f"Hello {owner_name},", "", heading, ""]
    for p in paragraphs:
        text_lines += [p, ""]
    for label, value in rows:
        text_lines.append(f"{label}: {value}")
    text_lines.append("")
    if cta:
        text_lines += [f"{cta[0]}: {cta[1]}", ""]
    if closing:
        text_lines += [closing, ""]
    text_lines += [
        "-- ",
        f"{BRAND} | Legal Metrology",
        "This is an automated status update. Please do not reply to this email.",
    ]
    text = "\n".join(text_lines)

    # ---- html ----
    color = _TONES.get(tone, _TONES["info"])
    para_html = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.55;color:#1f2937;">{escape(p)}</p>'
        for p in paragraphs
    )
    row_html = "".join(
        f'<tr><td style="padding:7px 12px;font-size:13px;color:#6b7280;white-space:nowrap;'
        f'border-bottom:1px solid #eef0f3;">{escape(label)}</td>'
        f'<td style="padding:7px 12px;font-size:14px;color:#111827;font-weight:600;'
        f'border-bottom:1px solid #eef0f3;">{escape(str(value))}</td></tr>'
        for label, value in rows
    )
    cta_html = ""
    if cta:
        cta_html = (
            f'<p style="margin:22px 0 6px;"><a href="{escape(cta[1], quote=True)}" '
            f'style="background:{color};color:#ffffff;text-decoration:none;font-weight:600;'
            f'font-size:14px;padding:11px 20px;border-radius:6px;display:inline-block;">'
            f"{escape(cta[0])}</a></p>"
        )
    closing_html = (
        f'<p style="margin:16px 0 0;font-size:13px;line-height:1.5;color:#4b5563;">{escape(closing)}</p>'
        if closing
        else ""
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;">
<tr><td style="background:{color};padding:16px 24px;color:#ffffff;font-size:13px;letter-spacing:.06em;font-weight:700;">{escape(BRAND.upper())} &middot; LEGAL METROLOGY</td></tr>
<tr><td style="padding:24px;">
<h1 style="margin:0 0 14px;font-size:20px;color:#111827;">{escape(heading)}</h1>
<p style="margin:0 0 14px;font-size:15px;color:#1f2937;">Hello {escape(owner_name)},</p>
{para_html}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;border:1px solid #eef0f3;border-radius:6px;">{row_html}</table>
{cta_html}
{closing_html}
</td></tr>
<tr><td style="padding:14px 24px;background:#f9fafb;font-size:12px;color:#6b7280;">This is an automated status update. Please do not reply to this email.</td></tr>
</table>
</td></tr></table>
</body></html>"""
    return subject, text, html


# --------------------------------------------------------------------------
# One builder per event. ctx keys are documented in owner_notifications.py.
# --------------------------------------------------------------------------

def _instrument_registered(ctx: dict):
    inst = ctx["instrument"]
    return _build(
        subject=f"Instrument registered: {inst.get('type')} ({inst.get('uiid')})",
        owner_name=ctx["owner_name"],
        heading="Your instrument has been registered",
        paragraphs=[
            f"Your {inst.get('type')} has been registered and assigned the UIID {inst.get('uiid')}.",
            "Registration alone does not make it verified. The next step is to submit it for verification "
            "so a Legal Metrology Officer can inspect it.",
        ],
        rows=_instrument_rows(inst),
        tone="info",
        cta=("Apply for verification", ctx["apply_url"]),
    )


def _application_submitted(ctx: dict):
    inst = ctx["instrument"]
    return _build(
        subject=f"Verification application received: {inst.get('uiid')}",
        owner_name=ctx["owner_name"],
        heading="Verification application received",
        paragraphs=[
            "We have received your verification application. It is now in the queue of the Legal Metrology "
            "office covering your location, and an officer will pick it up and schedule an inspection.",
            "You will get another email as soon as an officer is assigned.",
        ],
        rows=[("Application ID", ctx["application_id"]), *_instrument_rows(inst)],
        tone="info",
        cta=("Track this application", ctx["application_url"]),
    )


def _application_scheduled(ctx: dict):
    inst = ctx["instrument"]
    return _build(
        subject=f"Officer assigned, inspection scheduled: {inst.get('uiid')}",
        owner_name=ctx["owner_name"],
        heading="An officer has been assigned to your application",
        paragraphs=[
            "A Legal Metrology Officer has taken up your application and your instrument is now "
            "scheduled for inspection.",
            "Please keep the instrument accessible at the registered location, along with its serial "
            "number plate, so the officer can complete the physical check.",
        ],
        rows=[("Application ID", ctx["application_id"]), *_instrument_rows(inst)],
        tone="info",
        cta=("Track this application", ctx["application_url"]),
    )


def _inspection_passed(ctx: dict):
    inst = ctx["instrument"]
    return _build(
        subject=f"Inspection passed: {inst.get('uiid')}",
        owner_name=ctx["owner_name"],
        heading="Your instrument passed inspection",
        paragraphs=[
            "The inspection of your instrument is complete and it passed. Your application is now certified.",
            "Your certificate is being generated. We will email you again with the certificate as soon as it is ready.",
        ],
        rows=[
            ("Application ID", ctx["application_id"]),
            ("Inspected on", _fmt_date(ctx.get("inspected_at"))),
            ("Result", "PASS"),
            *_instrument_rows(inst),
        ],
        tone="success",
        cta=("View application", ctx["application_url"]),
    )


def _inspection_failed(ctx: dict):
    inst = ctx["instrument"]
    rows = [
        ("Application ID", ctx["application_id"]),
        ("Inspected on", _fmt_date(ctx.get("inspected_at"))),
        ("Result", "FAIL"),
    ]
    if ctx.get("observations"):
        rows.append(("Officer's observations", ctx["observations"]))
    rows += _instrument_rows(inst)
    return _build(
        subject=f"Inspection did not pass: {inst.get('uiid')}",
        owner_name=ctx["owner_name"],
        heading="Your instrument did not pass inspection",
        paragraphs=[
            "The inspection of your instrument is complete, but it did not meet the requirements, "
            "so this application has been rejected and no certificate has been issued.",
            "Please have the instrument repaired or recalibrated as needed. You can then submit a new "
            "verification application for it.",
        ],
        rows=rows,
        tone="danger",
        cta=("Apply again", ctx["reapply_url"]),
    )


def _certificate_issued(ctx: dict):
    inst = ctx["instrument"]
    rows = [
        ("Certificate no.", ctx["cert_no"]),
        ("Issued on", _fmt_date(ctx.get("issued_at"))),
        ("Valid until", _fmt_date(ctx.get("valid_until"))),
        *_instrument_rows(inst),
    ]
    if ctx.get("pdf_url"):
        rows.append(("Certificate PDF", ctx["pdf_url"]))
    return _build(
        subject=f"Certificate issued: {ctx['cert_no']}",
        owner_name=ctx["owner_name"],
        heading="Your verification certificate is ready",
        paragraphs=[
            f"Your instrument is now legally verified. Certificate {ctx['cert_no']} is valid until "
            f"{_fmt_date(ctx.get('valid_until'))}.",
            "We will remind you before it expires so you can renew in time. Anyone can confirm the "
            "certificate is genuine by scanning its QR code or using the verification link.",
        ],
        rows=rows,
        tone="success",
        cta=("View certificate", ctx["certificate_url"]),
        closing=f"Public verification link: {ctx['verify_url']}",
    )


def _expiry_reminder(ctx: dict):
    inst = ctx["instrument"]
    days = ctx["days_left"]
    when = "within 24 hours" if days <= 1 else f"in {days} days"
    return _build(
        subject=f"Certificate expires {when}: {inst.get('uiid')}",
        owner_name=ctx["owner_name"],
        heading=f"Your certificate expires {when}",
        paragraphs=[
            f"Certificate {ctx['cert_no']} for your {inst.get('type')} is valid until "
            f"{_fmt_date(ctx.get('valid_until'))}.",
            "Once it expires the instrument is no longer legally verified. Submit a re-verification "
            "application now so the inspection can be completed before the expiry date.",
        ],
        rows=[
            ("Certificate no.", ctx["cert_no"]),
            ("Valid until", _fmt_date(ctx.get("valid_until"))),
            ("Days remaining", str(days)),
            *_instrument_rows(inst),
        ],
        tone="warning" if days > 7 else "danger",
        cta=("Renew now", ctx["renew_url"]),
    )


def _certificate_expired(ctx: dict):
    inst = ctx["instrument"]
    return _build(
        subject=f"Certificate expired: {inst.get('uiid')}",
        owner_name=ctx["owner_name"],
        heading="Your certificate has expired",
        paragraphs=[
            f"Certificate {ctx['cert_no']} expired on {_fmt_date(ctx.get('valid_until'))}. "
            "Your instrument is no longer legally verified.",
            "Please submit a re-verification application as soon as possible to get a new certificate.",
        ],
        rows=[
            ("Certificate no.", ctx["cert_no"]),
            ("Expired on", _fmt_date(ctx.get("valid_until"))),
            *_instrument_rows(inst),
        ],
        tone="danger",
        cta=("Renew now", ctx["renew_url"]),
    )


_BUILDERS = {
    "instrument_registered": _instrument_registered,
    "application_submitted": _application_submitted,
    "application_scheduled": _application_scheduled,
    "inspection_passed": _inspection_passed,
    "inspection_failed": _inspection_failed,
    "certificate_issued": _certificate_issued,
    "expiry_reminder": _expiry_reminder,
    "certificate_expired": _certificate_expired,
}


def render(event: str, ctx: dict) -> tuple[str, str, str]:
    """Returns (subject, plain_text, html). Raises KeyError for an unknown event."""
    return _BUILDERS[event](ctx)
