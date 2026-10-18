from typing import Optional
from pydantic import BaseModel


class PendencyStatusCounts(BaseModel):
    submitted: int = 0
    scheduled: int = 0
    inspected: int = 0


class PendencyBucket(BaseModel):
    label: str
    min_days: int
    max_days: Optional[int] = None  # None = no upper limit
    count: int
    by_status: PendencyStatusCounts


class PendencyItem(BaseModel):
    application_id: str
    uiid: Optional[str] = None
    instrument_type: Optional[str] = None
    status: str
    application_type: str
    state_name: Optional[str] = None
    district_name: Optional[str] = None
    submitted_at: str
    age_days: int
    assigned: bool


class PendencyReport(BaseModel):
    generated_at: str
    target_days: int
    total_open: int
    unassigned: int
    over_target: int
    by_status: PendencyStatusCounts
    buckets: list[PendencyBucket]
    oldest: list[PendencyItem]


class DistrictRow(BaseModel):
    state_code: str
    state_name: str
    district_code: str
    district_name: str
    instruments: int
    open_applications: int
    overdue_applications: int
    verified: int
    expired: int


class DistrictReport(BaseModel):
    generated_at: str
    target_days: int
    totals: dict
    rows: list[DistrictRow]


class ReverificationInfo(BaseModel):
    status: str
    applied_on: str


class CaseRef(BaseModel):
    """The open enforcement case of an instrument, shown next to its row in a list."""
    id: str
    status: str  # open | notice_sent | escalated
    level: str   # lmo | gatc | admin (who holds it now)


class EnforcementItem(BaseModel):
    instrument_id: str
    uiid: Optional[str] = None
    instrument_type: Optional[str] = None
    owner_name: Optional[str] = None
    org_name: Optional[str] = None
    address_line: Optional[str] = None
    state_code: str
    state_name: Optional[str] = None
    district_code: str
    district_name: Optional[str] = None
    cert_no: Optional[str] = None
    valid_until: str
    days_overdue: int
    band: str  # recent | overdue | long_overdue
    reverification: Optional[ReverificationInfo] = None
    case: Optional[CaseRef] = None


class EnforcementSummary(BaseModel):
    lapsed: int
    reverification_applied: int
    no_reverification: int
    recent: int
    overdue: int
    long_overdue: int


class EnforcementReport(BaseModel):
    generated_at: str
    summary: EnforcementSummary
    total: int
    page: int
    page_size: int
    truncated: bool
    items: list[EnforcementItem]


class UncertifiedItem(BaseModel):
    instrument_id: str
    uiid: Optional[str] = None
    instrument_type: Optional[str] = None
    owner_name: Optional[str] = None
    org_name: Optional[str] = None
    address_line: Optional[str] = None
    state_code: str
    state_name: Optional[str] = None
    district_code: str
    district_name: Optional[str] = None
    registered_on: str
    days_since_registered: int
    application: Optional[ReverificationInfo] = None  # an open application is a mitigating note
    case: Optional[CaseRef] = None


class UncertifiedSummary(BaseModel):
    total: int
    applied: int
    not_applied: int


class UncertifiedReport(BaseModel):
    generated_at: str
    grace_days: int
    summary: UncertifiedSummary
    total: int
    page: int
    page_size: int
    truncated: bool
    items: list[UncertifiedItem]
