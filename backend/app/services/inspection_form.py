"""Checks a submitted inspection against the form for its instrument type, and shapes what is stored."""
from __future__ import annotations

from fastapi import HTTPException

from app.config import settings
from app.config.inspection_forms import form_spec
from app.models.inspection import InspectionCreate


def _error_pct(reference: float, error: float) -> float | None:
    return None if reference == 0 else round(error / reference * 100, 4)


def build_form_fields(payload: InspectionCreate, instrument_type: str | None) -> dict:
    """Validate the detailed part of an inspection and return the fields to store with it.

    Raises 422 with a plain message. Returns {} for a legacy submission (nothing detailed sent)
    when INSPECTION_FORM_STRICT is off.
    """
    provided = payload.test_points is not None or payload.checks is not None or payload.seal_number is not None
    is_pass = payload.result == "pass"

    if not provided:
        if is_pass and settings.INSPECTION_FORM_STRICT:
            raise HTTPException(
                status_code=422,
                detail="This inspection form is out of date. Reload the app, then record the test readings, "
                       "the checks and the seal number.",
            )
        return {}

    if not instrument_type:
        raise HTTPException(status_code=404, detail="Instrument not found for this application")
    spec = form_spec(instrument_type)
    known = {c["key"]: c for c in spec["checks"]}
    test = spec["test"]

    points = payload.test_points or []
    checks = payload.checks or {}

    unknown = sorted(set(checks) - set(known))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown check: {', '.join(unknown)}")
    if len(points) > test["max_points"]:
        raise HTTPException(status_code=422, detail=f"At most {test['max_points']} test readings can be recorded")

    if is_pass:
        if len(points) < test["min_points"]:
            raise HTTPException(
                status_code=422,
                detail=f"Record at least {test['min_points']} test reading{'s' if test['min_points'] != 1 else ''} "
                       f"before passing this instrument.",
            )
        unanswered = [c["label"] for c in spec["checks"] if c["key"] not in checks]
        if unanswered:
            raise HTTPException(status_code=422, detail=f"Answer every check before passing. Missing: {unanswered[0]}")
        failed = [c["label"] for c in spec["checks"] if c["required"] and checks.get(c["key"]) is not True]
        if failed:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot pass while a required check is not met: {failed[0]}. Record this as a Fail instead.",
            )
        if payload.seal_number is None:
            raise HTTPException(status_code=422, detail="Enter the seal number fixed on the instrument before passing it.")
    elif payload.seal_number is not None:
        raise HTTPException(status_code=422, detail="A seal is only fixed on an instrument that passes. Remove the seal number.")

    stored_points = []
    for pt in points:
        err = round(pt.indicated - pt.reference, 6)
        stored_points.append({
            "reference": pt.reference, "indicated": pt.indicated, "error": err,
            "error_pct": _error_pct(pt.reference, err),
        })

    out: dict = {
        "test_points": stored_points,
        "checks": [{"key": c["key"], "label": c["label"], "ok": bool(checks[c["key"]])}
                   for c in spec["checks"] if c["key"] in checks],
        "form": {
            "version": spec["form_version"],
            "instrument_type": instrument_type,
            "unit": test["unit"],
            "test_title": test["title"],
            "reference_label": test["reference_label"],
            "indicated_label": test["indicated_label"],
        },
    }
    if payload.seal_number:
        out["seal_number"] = payload.seal_number
    return out
