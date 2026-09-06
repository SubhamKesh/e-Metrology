from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    instrument_id: str


class HistoryEntry(BaseModel):
    from_status: Optional[str] = None
    to: str
    at: datetime
    changed_by: Optional[str] = None
    reason: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    instrument_id: str
    owner_id: str
    status: str
    assigned_officer_id: Optional[str] = None
    submitted_at: datetime
    history: list[HistoryEntry] = []
