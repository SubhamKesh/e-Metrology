from typing import Literal
from datetime import datetime
from pydantic import BaseModel


class InspectionCreate(BaseModel):
    application_id: str
    observations: str
    result: Literal["pass", "fail"]
    photos: list[str] = []  # Cloudinary URLs, uploaded separately via Kiran's /uploads/photo first


class InspectionOut(BaseModel):
    id: str
    application_id: str
    officer_id: str
    observations: str
    result: str
    photos: list[str] = []
    created_at: datetime  # frontend field name — stored internally as inspected_at
