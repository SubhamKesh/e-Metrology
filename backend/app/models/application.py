from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    instrument_id: str
    # Optional: the certificate being renewed. The server decides the application
    # type itself -- an instrument that already has a certificate is a renewal --
    # and links the newest certificate when this is omitted, so older clients and
    # emailed "Renew now" links keep working.
    previous_certificate_id: Optional[str] = None


class ScheduleIn(BaseModel):
    """Used by claim and schedule/reschedule. `date` is an India calendar date."""
    date: str = Field(..., description="YYYY-MM-DD")
    slot: str = Field(..., description="morning | afternoon")
    reason: Optional[str] = Field(default=None, max_length=300)


class AssignIn(ScheduleIn):
    officer_id: str


class ScheduleHistoryOut(BaseModel):
    kind: str
    date: str
    slot: str
    at: datetime
    by: Optional[str] = None
    reason: Optional[str] = None
    previous_date: Optional[str] = None
    previous_slot: Optional[str] = None


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
    # "initial" for a first verification, "renewal" for a re-verification that
    # follows an earlier certificate. Records created before this field existed
    # are initial.
    application_type: str = "initial"
    previous_certificate_id: Optional[str] = None
    previous_cert_no: Optional[str] = None
    # Expiry of the instrument's current certificate at the time of a renewal application.
    previous_valid_until: Optional[datetime] = None
    # Inspection schedule (None until an officer is assigned). `scheduled_date` is
    # an India calendar date, `slot` is "morning" or "afternoon".
    scheduled_date: Optional[str] = None
    slot: Optional[str] = None
    slot_label: Optional[str] = None
    schedule_history: list[ScheduleHistoryOut] = []
