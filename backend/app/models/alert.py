from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    certificate_id: str
    alert_type: str = "expiry_reminder"
    sent_at: datetime = Field(default_factory=datetime.utcnow)