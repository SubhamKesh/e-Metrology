from typing import Literal, Optional
from pydantic import BaseModel, Field, validator

from app.utils.validators import MAX_CODE_LENGTH, MAX_LONG_TEXT, validate_address


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

    # Codes are short fixed-format lookup keys, not free text — bounded
    # tightly so nothing can smuggle an oversized string into what should
    # be a lookup key. Whether the code actually *exists* is checked
    # separately against states_col/districts_col — see
    # app/utils/geo_validation.py:validate_state_district.
    state_code: str = Field(max_length=MAX_CODE_LENGTH)
    district_code: str = Field(max_length=MAX_CODE_LENGTH)
    # No Field(max_length=...) here on purpose — that would raise
    # Pydantic's default "ensure this value has at most N characters"
    # before validate_address ever runs. The length check now lives
    # entirely in validate_address, which gives a friendlier message.
    address_line: str  # shop/business address — free text is fine here,
    # it's only state_code/district_code that need to be canonical

    @validator("address_line")
    def _validate_address(cls, v):
        return validate_address(v)


class LocationOut(LocationIn):
    pass


class JurisdictionIn(BaseModel):
    """Scope for an lmo/gatc officer account.

    district_code=None means state-level scope (typically GATC / the
    state controller); district_code set means the officer is scoped to
    that single district (typically an LMO). admin accounts carry no
    jurisdiction at all — they're national scope by construction.
    """

    state_code: str = Field(max_length=MAX_CODE_LENGTH)
    district_code: Optional[str] = Field(default=None, max_length=MAX_CODE_LENGTH)


class JurisdictionOut(JurisdictionIn):
    pass
