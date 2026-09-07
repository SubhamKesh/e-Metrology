from typing import Optional
from pydantic import BaseModel


class NextExpiry(BaseModel):
    instrument_type: str
    uiid: str
    valid_until: str
    days_remaining: int


class OwnerDashboard(BaseModel):
    total_instruments: int
    verified: int
    pending: int
    expired: int
    next_expiry: Optional[NextExpiry] = None


class OfficerDashboard(BaseModel):
    assigned: int
    pending: int
    completed: int
    today_inspections: int


class StateBreakdown(BaseModel):
    location: str
    count: int


class AdminDashboard(BaseModel):
    total_instruments: int
    verified: int
    pending: int
    expired: int
    by_location: list[StateBreakdown]
