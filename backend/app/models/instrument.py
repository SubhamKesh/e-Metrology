from typing import Optional
from pydantic import BaseModel, Field


class InstrumentCreate(BaseModel):
    type: str  # e.g. "Electronic Weighing Machine"
    manufacturer: str
    model: str
    capacity: str  # e.g. "30 kg" — kept as string since units vary by instrument type
    serial_no: str = Field(min_length=1)
    location: Optional[str] = None  # shop/business address


class InstrumentOut(BaseModel):
    id: str
    owner_id: str
    type: str
    manufacturer: str
    model: str
    capacity: str
    serial_no: str
    location: Optional[str] = None
