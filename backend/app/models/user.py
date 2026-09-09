from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: str  # must be one of ROLES — validated in the router
    org_type: Optional[str] = None  # "LMO" or "GATC", only relevant for those roles
    org_name: Optional[str] = None
    contact: Optional[str] = None
    # Deliberately NO status field here — a registering user can never set
    # their own approval status. The router decides it based on role.


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    status: str
    org_type: Optional[str] = None
    org_name: Optional[str] = None
    contact: Optional[str] = None
    # True right after an admin creates an officer account with a temp
    # password; the frontend uses this to force a change-password screen
    # before letting the officer into the rest of the app.
    must_change_password: bool = False


class TokenResponse(BaseModel):
    user: UserOut
    token: str


class OfficerCreate(BaseModel):
    """Admin-only: provisions a new lmo/gatc account. There is no public
    equivalent of this model — officers can never submit this themselves."""

    name: str
    email: EmailStr
    role: str  # must be "lmo" or "gatc" — validated in the router
    org_type: Optional[str] = None  # "LMO" or "GATC"
    org_name: Optional[str] = None
    contact: Optional[str] = None


class OfficerCreatedOut(BaseModel):
    user: UserOut
    # Shown to the admin exactly once, in this response only. Never stored
    # or returned again — only its bcrypt hash lives in the DB afterwards.
    # Kept as a fallback even when `emailed` is True, in case the email
    # bounces or lands in spam.
    temp_password: str
    # Whether the credential email actually went out (SMTP configured and
    # the send succeeded). If False, the admin needs to share the temp
    # password with the officer themselves.
    emailed: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)