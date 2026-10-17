"""
What an officer records during a field verification, per instrument type.

One entry per type in ALLOWED_INSTRUMENT_TYPES (app/models/instrument.py). The same data is
served to the app by GET /api/v1/inspections/form-spec, so the form and the server's checks
cannot drift apart.

An inspection records
  * test points  - what the reference standard showed (reference) against what the instrument
                   showed (indicated). The server works out the error; it does NOT decide
                   pass/fail from it. Permitted errors depend on the class and rules of each
                   instrument, so the officer decides the result and the numbers are the evidence.
  * checks       - yes/no inspection items. A "required" check must be ticked for a Pass.
  * seal number  - the number on the verification stamp / seal fixed on a passed instrument.

Add a new instrument type in ONE place per file: instrument.py (type), instrument_specs.py (unit),
and here (what to test). A type with no entry here falls back to GENERIC_FORM, and
tests/test_inspections.py fails if a type is missing, so it is never missed silently.
"""
from __future__ import annotations

from app.config.instrument_specs import INSTRUMENT_SPECS

FORM_VERSION = 1

# Checks every instrument gets.
COMMON_CHECKS = [
    {"key": "markings_ok", "label": "Manufacturer's plate / markings are present and legible", "required": True},
    {"key": "no_tampering", "label": "No sign of tampering or unauthorised adjustment", "required": True},
]

DISPLAY_CHECK = {"key": "display_ok", "label": "Display or scale is clear and fully readable", "required": True}
ZERO_CHECK = {"key": "zero_ok", "label": "Reads zero with nothing applied", "required": True}
DAMAGE_CHECK = {"key": "no_damage", "label": "No visible damage, leaks or wear that could affect readings", "required": True}


def _test(title: str, reference_label: str, indicated_label: str, min_points: int, hint: str, unit: str | None = None) -> dict:
    return {
        "title": title,
        "reference_label": reference_label,
        "indicated_label": indicated_label,
        "min_points": min_points,
        "max_points": 12,
        "hint": hint,
        "unit": unit,  # None -> use the unit from INSTRUMENT_SPECS
    }


_WEIGHING = {
    "test": _test("Test loads", "Test mass applied", "Instrument shows", 3,
                  "Use certified test masses. Record at least three loads, e.g. low, middle and near the maximum."),
    "checks": [ZERO_CHECK, DISPLAY_CHECK, {"key": "level_stable", "label": "Instrument is level and the reading settles", "required": True}],
}

_METER = {
    "test": _test("Comparison with reference standard", "Reference standard shows", "Meter shows", 2,
                  "Run the meter against the reference standard and record at least two readings."),
    "checks": [DISPLAY_CHECK, DAMAGE_CHECK],
}

_GENERIC_POINTS = {
    "test": _test("Comparison with reference standard", "Reference standard shows", "Instrument shows", 2,
                  "Record at least two readings against the reference standard."),
    "checks": [DISPLAY_CHECK],
}

INSPECTION_FORMS: dict[str, dict] = {
    "Electronic Weighing Machine": _WEIGHING,
    "Platform Scale": _WEIGHING,
    "Non-Automatic Weighing Instrument": _WEIGHING,
    "Beam Scale": {**_WEIGHING, "checks": [ZERO_CHECK, {"key": "beam_free", "label": "Beam and knife edges move freely and are not worn", "required": True}]},
    "Automatic Rail Weighbridge": {
        "test": _test("Test loads", "Test mass applied", "Weighbridge shows", 3,
                      "Record at least three loads across the range."),
        "checks": [ZERO_CHECK, DISPLAY_CHECK, {"key": "deck_clear", "label": "Deck and approaches are clear of obstruction", "required": True}],
    },
    "Load Cell": {
        "test": _test("Test loads", "Test mass applied", "Load cell output (converted to mass)", 3,
                      "Record at least three loads across the range."),
        "checks": [DAMAGE_CHECK, {"key": "mount_ok", "label": "Mounting is secure and cabling is undamaged", "required": True}],
    },
    "Weights": {
        "test": _test("Weight comparison", "Standard mass", "Measured mass of this weight", 1,
                      "Compare against the standard mass and record the measured value."),
        "checks": [{"key": "nominal_marked", "label": "Nominal value is clearly marked", "required": True},
                   {"key": "no_wear", "label": "No visible damage, corrosion or loss of material", "required": True}],
    },
    "Fuel Dispensing Unit": {
        "test": _test("Delivery test", "Quantity in the test measure", "Quantity shown on the dispenser", 2,
                      "Deliver into a calibrated test measure. Record at least two deliveries.", unit="L"),
        "checks": [DISPLAY_CHECK,
                   {"key": "no_air_leaks", "label": "No air in the line and no leaks at hose, nozzle or joints", "required": True},
                   {"key": "totaliser_ok", "label": "Totaliser and price display agree with the delivery", "required": True}],
    },
    "Water Meter": _METER,
    "Flow Meter": {**_METER, "test": _test("Comparison with reference standard", "Reference standard shows", "Meter shows", 2,
                                           "Run the meter against the reference standard and record at least two readings.", unit="L")},
    "Gas Meter": {**_METER, "test": _test("Comparison with reference standard", "Reference standard shows", "Meter shows", 2,
                                          "Run the meter against the reference standard and record at least two readings.", unit="m³")},
    "Energy Meter": _METER,
    "Clinical Thermometer": {
        "test": _test("Temperature comparison", "Reference thermometer shows", "Thermometer shows", 2,
                      "Compare in a stirred bath at two temperatures within the normal range."),
        "checks": [DISPLAY_CHECK, DAMAGE_CHECK],
    },
    "Tape Measure": {
        "test": _test("Length comparison", "Reference length", "Length on the tape", 2,
                      "Compare against a reference scale at two or more lengths."),
        "checks": [{"key": "graduations_ok", "label": "Graduations are clear, complete and not worn", "required": True},
                   {"key": "end_ok", "label": "End hook or tip is not bent or loose, and the tape is not kinked", "required": True}],
    },
    "Moisture Meter": _GENERIC_POINTS,
    "Speed Meter": _GENERIC_POINTS,
    "Breath Analyser": _GENERIC_POINTS,
    "Counter Machine": {
        "test": _test("Count test", "Actual count", "Count shown by the machine", 2,
                      "Run a counted batch and record at least two runs.", unit="pcs"),
        "checks": [DISPLAY_CHECK],
    },
}

GENERIC_FORM = _GENERIC_POINTS


def form_spec(instrument_type: str) -> dict:
    """Everything the app and the server need to know about the form for one instrument type."""
    base = INSPECTION_FORMS.get(instrument_type, GENERIC_FORM)
    unit = base["test"]["unit"] or INSTRUMENT_SPECS.get(instrument_type, {}).get("unit", "")
    # Type-specific items first, the two common ones last.
    checks = [dict(c) for c in base["checks"]] + [dict(c) for c in COMMON_CHECKS]
    return {
        "form_version": FORM_VERSION,
        "instrument_type": instrument_type,
        "test": {**base["test"], "unit": unit},
        "checks": checks,
        "seal": {"label": "Verification stamp / seal number", "required_on_pass": True},
    }
