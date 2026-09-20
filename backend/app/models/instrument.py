from typing import Literal, Optional
from pydantic import BaseModel

from app.models.geo import LocationIn, LocationOut

# Instrument types recognized by the platform. Extend this list (and the
# Literal below) together whenever a new instrument category is supported —
# they're kept in sync deliberately so mismatches fail loudly at import time
# instead of silently accepting bad data.
ALLOWED_INSTRUMENT_TYPES = [
    "Electronic Weighing Machine",
    "Fuel Dispensing Unit",
    "Platform Scale",
    "Water Meter",
    "Clinical Thermometer",
    "Automatic Rail Weighbridge",
    "Tape Measure",
    "Non-Automatic Weighing Instrument",
    "Load Cell",
    "Beam Scale",
    "Counter Machine",
    "Weights",
    "Gas Meter",
    "Energy Meter",
    "Moisture Meter",
    "Speed Meter",
    "Breath Analyser",
    "Flow Meter",
]

InstrumentType = Literal[
    "Electronic Weighing Machine",
    "Fuel Dispensing Unit",
    "Platform Scale",
    "Water Meter",
    "Clinical Thermometer",
    "Automatic Rail Weighbridge",
    "Tape Measure",
    "Non-Automatic Weighing Instrument",
    "Load Cell",
    "Beam Scale",
    "Counter Machine",
    "Weights",
    "Gas Meter",
    "Energy Meter",
    "Moisture Meter",
    "Speed Meter",
    "Breath Analyser",
    "Flow Meter",
]


class InstrumentCreate(BaseModel):
    type: InstrumentType
    manufacturer: str
    model: str
    capacity: str  # e.g. "30 kg" — kept as string since units vary by instrument type
    serial_no: str  # manufacturer-assigned serial number, used for duplicate detection
    location: LocationIn  # state_code/district_code + address — required, not optional:
    # this is what makes jurisdiction routing to the right officer possible at all.
    # uiid is deliberately NOT here — it's backend-generated (see
    # app/services/uiid_generator.py), never supplied by the client.


class InstrumentOut(BaseModel):
    id: str
    owner_id: str
    type: str
    manufacturer: str
    model: str
    capacity: str
    serial_no: str
    uiid: str  # government-issued unique instrument ID, e.g. "LM-000001"
    location: LocationOut


class InstrumentTypeSpec(BaseModel):
    """Drives the capacity field's input widget/unit on the frontend —
    see app/config/instrument_specs.py for the actual data."""

    type: str
    unit: str
    input_type: str
    step: str
    placeholder: str