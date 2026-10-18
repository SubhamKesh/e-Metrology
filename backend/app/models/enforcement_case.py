from typing import Optional

from pydantic import BaseModel, Field


class OpenCaseIn(BaseModel):
    instrument_id: str = Field(..., min_length=1, max_length=64)


class NoticeIn(BaseModel):
    # Optional line from the officer, added to the standard notice text.
    message: Optional[str] = Field(default=None, max_length=500)


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class EscalateIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class CloseIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class CaseEventOut(BaseModel):
    at: str
    action: str  # opened | notice | note | escalated | resolved
    by_name: Optional[str] = None  # None = done by the system
    by_role: Optional[str] = None
    text: Optional[str] = None
    to_level: Optional[str] = None
    emailed: Optional[bool] = None  # notices only: was an email sent to the owner


class CasePermissions(BaseModel):
    note: bool
    notice: bool
    escalate: bool
    close: bool
    notice_available_on: Optional[str] = None  # set while a recent notice blocks sending another


class CaseInstrument(BaseModel):
    id: str
    uiid: Optional[str] = None
    type: Optional[str] = None
    address_line: Optional[str] = None


class CaseOwner(BaseModel):
    name: Optional[str] = None
    org_name: Optional[str] = None


class CaseListItem(BaseModel):
    id: str
    kind: str  # lapsed | never_certified
    status: str  # open | notice_sent | escalated | resolved
    level: str  # lmo | gatc | admin
    instrument: CaseInstrument
    owner: CaseOwner
    state_name: Optional[str] = None
    district_name: Optional[str] = None
    opened_at: str
    last_notice_at: Optional[str] = None
    notice_count: int = 0
    escalation_due: bool = False
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None  # renewed | certified | closed
    held_by_me: bool = False


class CaseOut(CaseListItem):
    state_code: Optional[str] = None
    district_code: Optional[str] = None
    opened_by_name: Optional[str] = None
    escalation_after_days: int
    events: list[CaseEventOut]
    can: CasePermissions
    # Facts about why the instrument is on the list (newest certificate / registration date).
    cert_no: Optional[str] = None
    valid_until: Optional[str] = None
    registered_on: Optional[str] = None


class CaseSummary(BaseModel):
    active: int
    open: int
    notice_sent: int
    escalated: int
    escalation_due: int
    with_me: int
    resolved: int


class CaseListReport(BaseModel):
    generated_at: str
    summary: CaseSummary
    total: int
    page: int
    page_size: int
    items: list[CaseListItem]


class OwnerNoticeOut(BaseModel):
    case_id: str
    kind: str
    instrument_id: str
    uiid: Optional[str] = None
    instrument_type: Optional[str] = None
    sent_at: str
    message: Optional[str] = None
    issued_by: str  # a role title, never a person's name
    notice_count: int
