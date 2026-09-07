from typing import Literal, Optional
from pydantic import BaseModel

# Instrument types recognized by the platform. Extend this list (and the
# Literal below) together whenever a new instrument category is supported —
# they're kept in sync deliberately so mismatches fail loudly at import time
# instead of silently accepting bad data.
ALLOWED_INSTRUMENT_TYPES = [
    "Electronic Weighing Machine",
    "Fuel Dispensing Unit",
    "Platform Scale",
]

InstrumentType = Literal[
    "Electronic Weighing Machine",
    "Fuel Dispensing Unit",
    "Platform Scale",
]


class InstrumentCreate(BaseModel):
    type: InstrumentType
    manufacturer: str
    model: str
    capacity: str  # e.g. "30 kg" — kept as string since units vary by instrument type
    serial_no: str  # manufacturer-assigned serial number, used for duplicate detection
    location: Optional[str] = None  # shop/business address
    # uiid is deliberately NOT here — it's backend-generated (see
    # app/services/uiid_generator.py), never supplied by the client.


class InstrumentOut(BaseModel):
    id: str
    owner_id: str
    type: InstrumentType
    manufacturer: str
    model: str
    capacity: str
    serial_no: str
    uiid: str  # government-issued unique instrument ID, e.g. "LM-000001"
    location: Optional[str] = None