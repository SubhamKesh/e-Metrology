from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    instrument_id: str


class HistoryEntry(BaseModel):
    # Field names match frontend's ApplicationHistoryEntry exactly:
    # {status, at, by?, note?}. Internally, status_transition.py still
    # writes {from, to, at, changed_by, reason} to MongoDB — the router's
    # to_application_out() maps between the two shapes, so status_transition.py
    # (shared with Kiran's code) didn't need to change.
    status: str
    at: datetime
    by: Optional[str] = None
    note: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    instrument_id: str
    owner_id: str
    status: str
    assigned_officer_id: Optional[str] = None
    created_at: datetime
    history: list[HistoryEntry] = []
    # Denormalized from the instrument at submission time (see
    # routers/applications.py: submit_application) so jurisdiction
    # filtering/routing is a plain indexed match, not a join per query.
    state_code: str
    district_code: str
