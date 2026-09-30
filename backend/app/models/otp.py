from typing import Literal
from pydantic import BaseModel, validator

# Email is the only supported OTP channel.
Channel = Literal["email"]


class OtpSendRequest(BaseModel):
    channel: Channel
    identifier: str

    @validator("identifier")
    def _validate_identifier(cls, v):
        v = v.strip().lower()
        if not v:
            raise ValueError("An email address is required.")
        return v


class OtpVerifyRequest(OtpSendRequest):
    code: str

    @validator("code")
    def _validate_code(cls, v):
        v = v.strip()
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Enter the 6-digit code exactly as sent.")
        return v
