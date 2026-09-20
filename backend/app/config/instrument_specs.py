"""
One entry per type in ALLOWED_INSTRUMENT_TYPES (app/models/instrument.py) —
drives the "capacity" field's input widget and unit on the frontend via
GET /api/v1/instruments/meta/types, instead of the frontend hardcoding a
second copy of this mapping that could drift out of sync.

unit          — shown as a suffix next to the input, and appended to the
                numeric value to build the stored `capacity` string (kept
                as a plain string in the DB — see InstrumentCreate.capacity
                — since it already reads fine as "30 kg", "0.5 %", etc.)
input_type    — "number" for everything here; kept as a field (not just
                assumed) so a future non-numeric type doesn't need a schema
                change, only a new spec entry.
step          — HTML input step attribute; finer for small-scale
                measurements (thermometers, moisture %), coarser for
                large-capacity ones (rail weighbridges).
"""

INSTRUMENT_SPECS = {
    "Electronic Weighing Machine": {"unit": "kg", "input_type": "number", "step": "0.01", "placeholder": "30"},
    "Fuel Dispensing Unit": {"unit": "L/min", "input_type": "number", "step": "0.1", "placeholder": "20"},
    "Platform Scale": {"unit": "kg", "input_type": "number", "step": "1", "placeholder": "500"},
    "Water Meter": {"unit": "m³", "input_type": "number", "step": "0.001", "placeholder": "1.5"},
    "Clinical Thermometer": {"unit": "°C", "input_type": "number", "step": "0.1", "placeholder": "42"},
    "Automatic Rail Weighbridge": {"unit": "tonnes", "input_type": "number", "step": "1", "placeholder": "150"},
    "Tape Measure": {"unit": "m", "input_type": "number", "step": "0.01", "placeholder": "30"},
    "Non-Automatic Weighing Instrument": {"unit": "kg", "input_type": "number", "step": "0.01", "placeholder": "30"},
    "Load Cell": {"unit": "kg", "input_type": "number", "step": "1", "placeholder": "1000"},
    "Beam Scale": {"unit": "kg", "input_type": "number", "step": "0.1", "placeholder": "20"},
    "Counter Machine": {"unit": "pcs/min", "input_type": "number", "step": "1", "placeholder": "500"},
    "Weights": {"unit": "kg", "input_type": "number", "step": "0.001", "placeholder": "1"},
    "Gas Meter": {"unit": "m³/h", "input_type": "number", "step": "0.01", "placeholder": "6"},
    "Energy Meter": {"unit": "kWh", "input_type": "number", "step": "0.01", "placeholder": "10"},
    "Moisture Meter": {"unit": "%", "input_type": "number", "step": "0.1", "placeholder": "14"},
    "Speed Meter": {"unit": "km/h", "input_type": "number", "step": "1", "placeholder": "120"},
    "Breath Analyser": {"unit": "mg/L", "input_type": "number", "step": "0.001", "placeholder": "0.35"},
    "Flow Meter": {"unit": "L/min", "input_type": "number", "step": "0.1", "placeholder": "50"},
}
