from typing import Literal
from pydantic import BaseModel, validator

from app.models.geo import LocationIn, LocationOut
from app.utils.validators import validate_capacity_number, validate_manufacturer, validate_model, validate_serial_no

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
    # No Field(max_length=...) on manufacturer/model/serial_no on purpose —
    # Pydantic checks a field's own constraints before running @validators,
    # so a Field(max_length=...) here would win every time and the
    # validate_* calls below would never run. The length checks now live
    # entirely in validate_manufacturer/validate_model/validate_serial_no,
    # in app/utils/validators.py, which raise the friendlier messages.
    manufacturer: str
    model: str
    # The client submits just the bare number (e.g. "30") — the unit is
    # looked up from app/config/instrument_specs.py by `type` and appended
    # server-side (see routers/instruments.py: register_instrument), so the
    # stored value still ends up "30 kg" same as before this change; only
    # what the client is allowed to *submit* is different.
    capacity: str
    serial_no: str  # manufacturer-assigned serial number, used for duplicate detection
    location: LocationIn  # state_code/district_code + address — required, not optional:
    # this is what makes jurisdiction routing to the right officer possible at all.
    # uiid is deliberately NOT here — it's backend-generated (see
    # app/services/uiid_generator.py), never supplied by the client.

    @validator("manufacturer")
    def _validate_manufacturer(cls, v):
        return validate_manufacturer(v)

    @validator("capacity")
    def _validate_capacity(cls, v):
        return validate_capacity_number(v)

    @validator("model")
    def _validate_model(cls, v):
        return validate_model(v)

    @validator("serial_no")
    def _validate_serial_no(cls, v):
        return validate_serial_no(v)


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