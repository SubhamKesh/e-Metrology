from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    instrument_id: str
    slot: str
    label: str
    filename: str
    content_type: str
    size: int
    url: str
    uploaded_at: datetime


class DocumentSlotOut(BaseModel):
    slot: str
    label: str
    hint: str
    required: bool
    document: Optional[DocumentOut] = None


class DocumentSlotsOut(BaseModel):
    # "initial" (first verification) or "renewal" (the instrument already has a certificate).
    application_type: str
    # True when every required slot is filled, i.e. the owner may submit the application.
    complete: bool
    # True while an application is being processed: the documents are then locked.
    locked: bool
    slots: list[DocumentSlotOut]
