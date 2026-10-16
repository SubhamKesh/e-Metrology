from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field

from app.utils.validators import MAX_NOTE_TEXT


class InspectionLocation(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000)


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


class InspectionOut(BaseModel):
    id: str
    application_id: str
    officer_id: str
    observations: str
    result: str
    photos: list[str] = []
    identity_method: str = "manual"
    location: InspectionLocation | None = None
    submitted_offline: bool = False  # captured on the device before the server received it
    created_at: datetime  # frontend field name — stored internally as inspected_at
