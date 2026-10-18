from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ValidityRuleIn(BaseModel):
    days: int


class ValidityRuleOut(BaseModel):
    type: str
    days: int
    label: str
    default_days: int
    is_default: bool
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None


class ValidityRulesOut(BaseModel):
    default_days: int
    default_label: str
    min_days: int
    max_days: int
    items: List[ValidityRuleOut]
