from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid

class Certificate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    inspection_id: str
    cert_no: str
    qr_url: Optional[str] = None
    pdf_url: Optional[str] = None
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime