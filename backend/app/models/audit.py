from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: str
    event: str
    outcome: str
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: List[AuditLogOut]
    total: int
    page: int
    page_size: int
    # Every event name that can appear, for the viewer's filter dropdown.
    events: List[str]
