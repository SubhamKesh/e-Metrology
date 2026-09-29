from typing import Optional
from pydantic import BaseModel, EmailStr, validator

from app.models.geo import JurisdictionIn, JurisdictionOut
from app.utils.validators import (
    validate_email,
    validate_name,
    validate_org_name,
    validate_password,
    validate_phone,
)


class UserRegister(BaseModel):
    # No Field(max_length=...)/Field(min_length=...) on name/org_name/
    # password — same reasoning as email above: validate_name/
    # validate_org_name/validate_password (in app/utils/validators.py)
    # give friendlier messages, which a Field-level constraint would
    # otherwise shadow by winning first.
    name: str
    email: str
    password: str
    role: str  # must be one of ROLES — validated in the router
    org_type: Optional[str] = None  # "LMO" or "GATC", only relevant for those roles
    org_name: Optional[str] = None
    contact: Optional[str] = None
    # Deliberately NO status field here — a registering user can never set
    # their own approval status. The router decides it based on role.

    @validator("name")
    def _validate_name(cls, v):
        return validate_name(v)

    @validator("email")
    def _validate_email(cls, v):
        return validate_email(v)

    @validator("password")
    def _validate_password(cls, v):
        return validate_password(v)

    @validator("org_name")
    def _validate_org_name(cls, v):
        return validate_org_name(v)

    @validator("contact")
    def _validate_contact(cls, v):
        return validate_phone(v)


class UserLogin(BaseModel):
    # str, not EmailStr — same reasoning as UserRegister.email above: a
    # human is typing this into a form, so it gets the friendlier message.
    # UserOut.email below stays EmailStr on purpose — that's re-serializing
    # an email that's already stored and already valid, not user input.
    email: str
    password: str

    @validator("email")
    def _validate_email(cls, v):
        return validate_email(v)


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    status: str
    org_type: Optional[str] = None
    org_name: Optional[str] = None
    contact: Optional[str] = None
    # Set by POST /otp/verify (see app/routers/otp.py) once the owner/
    # officer proves they control this email or phone. False for every
    # account until then — including accounts created before OTP
    # verification existed, which is intentional: it means anything
    # gating on these flags fails safe for pre-existing accounts too.
    is_email_verified: bool = False
    is_phone_verified: bool = False
    jurisdiction: Optional[JurisdictionOut] = None  # set for lmo/gatc, None for owner/admin
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
    # str, not EmailStr — same reasoning as UserRegister.email above.
    email: str
    role: str  # must be "lmo" or "gatc" — validated in the router
    org_type: Optional[str] = None  # "LMO" or "GATC"
    org_name: Optional[str] = None
    contact: Optional[str] = None
    # Required for both roles: district_code set -> LMO scoped to that
    # district; district_code omitted -> state-level scope, the normal
    # shape for a GATC/state-controller account. Validated + enforced in
    # routers/admin_users.py and middleware/auth.py.
    jurisdiction: JurisdictionIn

    @validator("name")
    def _validate_name(cls, v):
        return validate_name(v)

    @validator("email")
    def _validate_email(cls, v):
        return validate_email(v)

    @validator("org_name")
    def _validate_org_name(cls, v):
        return validate_org_name(v)

    @validator("contact")
    def _validate_contact(cls, v):
        return validate_phone(v)


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
    new_password: str

    @validator("new_password")
    def _validate_new_password(cls, v):
        return validate_password(v)