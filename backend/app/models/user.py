from typing import List, Optional
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
    # "Remember me" checkbox. Defaults to False so older clients (and the
    # existing tests) that don't send it keep today's behaviour exactly.
    remember_me: bool = False

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
    # Whether two-step verification (authenticator app) is set up. Lets the
    # admin's officer list show who still has to enrol.
    mfa_enabled: bool = False


class TokenResponse(BaseModel):
    user: UserOut
    token: str
    # Whether "Remember me" was actually honoured. Always False for officer
    # and admin accounts even if the client asked for it — the frontend uses
    # this (not its own checkbox) to decide where to keep the session.
    remember_me: bool = False


class LoginResponse(BaseModel):
    """What /auth/login and the /auth/mfa/* endpoints return.

    Either a finished session (`user` + `token`), or — for officer/admin
    accounts whose PASSWORD was accepted but who still owe the second step —
    just an `mfa_token` plus a flag saying which step comes next. No token,
    no cookie and no user data is released until the second step passes.
    """

    user: Optional[UserOut] = None
    token: Optional[str] = None
    remember_me: bool = False
    # Second step pending: enter a code from the authenticator app.
    mfa_required: bool = False
    # Second step pending, and the account has no authenticator yet: enrol one.
    mfa_setup_required: bool = False
    mfa_token: Optional[str] = None
    # Only returned once, when enrolment completes.
    recovery_codes: Optional[List[str]] = None
    # Only set when a recovery code (not an app code) was just used.
    recovery_codes_remaining: Optional[int] = None


class MfaTokenRequest(BaseModel):
    mfa_token: str


class MfaCodeRequest(BaseModel):
    mfa_token: str
    # 6-digit authenticator code, or a recovery code like "k7m2x-q9d4p".
    code: str

    @validator("code")
    def _validate_code(cls, v):
        v = v.strip()
        if not v or len(v) > 32:
            raise ValueError("Enter the code from your authenticator app.")
        return v


class MfaSetupResponse(BaseModel):
    secret: str  # base32, for manual entry
    otpauth_uri: str
    qr_data_uri: str  # PNG, ready for <img src>


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


class ChangePasswordResponse(UserOut):
    """change-password signs the account out of every session (token_version
    bump + all refresh tokens revoked), then issues a fresh session for the
    device that made the change — so the response carries the new access
    token (and the new refresh cookie is set), exactly like login."""

    token: str
    remember_me: bool = False


class ForgotPasswordRequest(BaseModel):
    email: str

    @validator("email")
    def _validate_email(cls, v):
        return validate_email(v)


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str

    @validator("email")
    def _validate_email(cls, v):
        return validate_email(v)

    @validator("code")
    def _validate_code(cls, v):
        v = v.strip()
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Enter the 6-digit code exactly as sent.")
        return v

    @validator("new_password")
    def _validate_new_password(cls, v):
        return validate_password(v)
