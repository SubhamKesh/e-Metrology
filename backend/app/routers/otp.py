import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config.db import users_col
from app.config.settings import OTP_SEND_COOLDOWN_SECONDS
from app.models.otp import OtpSendRequest, OtpVerifyRequest
from app.rate_limit import RATE_LIMIT_AUTH, RATE_LIMIT_OTP_SEND, limiter
from app.services.audit import log_event
from app.services.mailer import send_email
from app.services.otp import generate_and_store_otp, otp_sent_within, verify_otp

logger = logging.getLogger("app.otp")

router = APIRouter(prefix="/api/v1/otp", tags=["otp"])

PURPOSE = "email_verify"


@router.post("/send")
@limiter.limit(RATE_LIMIT_OTP_SEND)
def send_otp(payload: OtpSendRequest, request: Request, background_tasks: BackgroundTasks):
    """Emails a signup verification code.

    Limited two ways so it can't be used to spam an inbox the caller doesn't
    own: a per-IP limit (RATE_LIMIT_OTP_SEND) and a per-ADDRESS cooldown
    (OTP_SEND_COOLDOWN_SECONDS) that holds no matter how many IPs ask. The
    cooldown applies to every address equally, whether or not it has an
    account, so telling the caller to wait reveals nothing about who is
    registered. The email is sent in a background task so a slow SMTP server
    doesn't hold the request open.
    """
    if otp_sent_within(identifier=payload.identifier, purpose=PURPOSE, seconds=OTP_SEND_COOLDOWN_SECONDS):
        log_event("signup_otp_requested", outcome="ignored", request=request, email=payload.identifier, detail="cooldown")
        raise HTTPException(
            status_code=429,
            detail=f"A code was just sent. Please wait {OTP_SEND_COOLDOWN_SECONDS} seconds before requesting another.",
            headers={"Retry-After": str(OTP_SEND_COOLDOWN_SECONDS)},
        )

    code = generate_and_store_otp(identifier=payload.identifier, purpose=PURPOSE)
    background_tasks.add_task(
        send_email,
        to=payload.identifier,
        subject="Your MaapSetu verification code",
        body=f"Your verification code is {code}. It expires in 10 minutes.\n\n"
        "If you didn't request this, you can ignore this email.",
    )
    log_event("signup_otp_requested", outcome="success", request=request, email=payload.identifier, detail="code_sent")
    # Deliberately doesn't reveal whether an account with this email exists.
    return {"sent": True}


@router.post("/verify")
@limiter.limit(RATE_LIMIT_AUTH)
def verify_otp_endpoint(payload: OtpVerifyRequest, request: Request):
    """Works both for an existing account (flags it verified) and for a
    brand-new signup (no user doc yet, so the update is a no-op, and the
    proof record left by verify_otp() is what POST /auth/register checks)."""
    ok, error = verify_otp(identifier=payload.identifier, purpose=PURPOSE, submitted_code=payload.code)
    if not ok:
        raise HTTPException(status_code=400, detail=error)

    users_col.update_one({"email": payload.identifier}, {"$set": {"is_email_verified": True}})
    return {"verified": True}
