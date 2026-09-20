from typing import Literal, Optional
from pydantic import BaseModel


class StateOut(BaseModel):
    code: str
    name: str
    type: Literal["state", "ut"]


class DistrictOut(BaseModel):
    code: str
    name: str
    state_code: str


class LocationIn(BaseModel):
    """What a client submits when registering an instrument."""

    state_code: str
    district_code: str
    address_line: str  # shop/business address — free text is fine here,
    # it's only state_code/district_code that need to be canonical


class LocationOut(LocationIn):
    pass


class JurisdictionIn(BaseModel):
    """Scope for an lmo/gatc officer account.

    district_code=None means state-level scope (typically GATC / the
    state controller); district_code set means the officer is scoped to
    that single district (typically an LMO). admin accounts carry no
    jurisdiction at all — they're national scope by construction.
    """

    state_code: str
    district_code: Optional[str] = None


class JurisdictionOut(JurisdictionIn):
    pass
