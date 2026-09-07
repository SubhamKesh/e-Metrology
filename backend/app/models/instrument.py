from typing import Optional
from pydantic import BaseModel


class InstrumentCreate(BaseModel):
    type: str  # e.g. "Electronic Weighing Machine"
    manufacturer: str
    model: str
    capacity: str  # e.g. "30 kg" — kept as string since units vary by instrument type
    location: Optional[str] = None  # shop/business address
    # uiid is deliberately NOT here — it's backend-generated (see
    # app/services/uiid_generator.py), never supplied by the client.


class InstrumentOut(BaseModel):
    id: str
    owner_id: str
    type: str
    manufacturer: str
    model: str
    capacity: str
    uiid: str  # government-issued unique instrument ID, e.g. "LM-000001"
    location: Optional[str] = None
