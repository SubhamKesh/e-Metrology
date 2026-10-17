import re
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.utils.validators import MAX_NOTE_TEXT


class InspectionLocation(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000)


SEAL_RE = re.compile(r"^[A-Z0-9][A-Z0-9 /._-]{2,31}$")
_NUM = dict(ge=-1e9, le=1e9, allow_inf_nan=False)


class TestPointIn(BaseModel):
    __test__ = False  # not a pytest class, despite the name
    reference: float = Field(**_NUM)  # what the reference standard showed
    indicated: float = Field(**_NUM)  # what the instrument showed


class TestPointOut(BaseModel):
    __test__ = False
    reference: float
    indicated: float
    error: float  # indicated - reference
    error_pct: float | None = None  # of the reference; None when the reference is zero


class CheckOut(BaseModel):
    key: str
    label: str  # kept with the record, so it still reads the same if the form wording changes later
    ok: bool


class FormSnapshot(BaseModel):
    instrument_type: str
    unit: str
    test_title: str
    reference_label: str
    indicated_label: str


class InspectionCreate(BaseModel):
    application_id: str
    observations: str = Field(max_length=MAX_NOTE_TEXT)
    result: Literal["pass", "fail"]
    photos: list[str] = []  # Cloudinary URLs, uploaded separately via Kiran's /uploads/photo first
    identity_method: Literal["qr", "manual"] = "manual"  # how the instrument UIID was captured
    location: InspectionLocation  # officer's GPS fix at submission (mandatory)
    # Offline support. The app generates client_id once per inspection, so a retried or
    # queued-then-synced submission is applied exactly once. captured_at is when the
    # officer actually pressed Submit (may be hours before the server sees it).
    client_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    captured_at: datetime | None = None
    # The detailed form (see app/config/inspection_forms.py). Required for a Pass unless
    # INSPECTION_FORM_STRICT is off; the server decides what counts as complete, not the client.
    test_points: list[TestPointIn] | None = Field(default=None, max_length=12)
    checks: dict[str, bool] | None = None
    seal_number: str | None = None  # verification stamp / seal fixed on a passed instrument

    @field_validator("seal_number")
    @classmethod
    def _seal(cls, v):
        if v is None:
            return None
        v = " ".join(v.split()).upper()
        if v == "":
            return None
        if not SEAL_RE.match(v):
            raise ValueError("Seal number must be 3-32 characters: letters, digits, space and / . _ -")
        return v


class InspectionOut(BaseModel):
    id: str
    application_id: str
    officer_id: str | None = None  # hidden from owners
    observations: str
    result: str
    photos: list[str] = []
    identity_method: str = "manual"
    location: InspectionLocation | None = None
    seal_number: str | None = None
    test_points: list[TestPointOut] = []
    checks: list[CheckOut] = []
    form: FormSnapshot | None = None  # None on records made before the detailed form existed
    submitted_offline: bool = False  # captured on the device before the server received it
    created_at: datetime  # frontend field name — stored internally as inspected_at
