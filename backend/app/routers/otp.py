import logging

from fastapi import APIRouter, HTTPException

from app.config.db import users_col
from app.models.otp import OtpSendRequest, OtpVerifyRequest
from app.services.mailer import send_email
from app.services.otp import generate_and_store_otp, verify_otp

logger = logging.getLogger("app.otp")

router = APIRouter(prefix="/api/v1/otp", tags=["otp"])

PURPOSE = "email_verify"

# TODO: rate-limit /send using the existing middleware/ infrastructure so
# it can't be used to spam an email address the caller doesn't own.


@router.post("/send")
def send_otp(payload: OtpSendRequest):
    code = generate_and_store_otp(identifier=payload.identifier, purpose=PURPOSE)
    send_email(
        to=payload.identifier,
        subject="Your MaapSetu verification code",
        body=f"Your verification code is {code}. It expires in 10 minutes.\n\n"
        "If you didn't request this, you can ignore this email.",
    )
    # Deliberately doesn't reveal whether an account with this email exists.
    return {"sent": True}


@router.post("/verify")
def verify_otp_endpoint(payload: OtpVerifyRequest):
    """Works both for an existing account (flags it verified) and for a
    brand-new signup (no user doc yet, so the update is a no-op, and the
    proof record left by verify_otp() is what POST /auth/register checks)."""
    ok, error = verify_otp(identifier=payload.identifier, purpose=PURPOSE, submitted_code=payload.code)
    if not ok:
        raise HTTPException(status_code=400, detail=error)

    users_col.update_one({"email": payload.identifier}, {"$set": {"is_email_verified": True}})
    return {"verified": True}