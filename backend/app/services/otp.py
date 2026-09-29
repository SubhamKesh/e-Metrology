"""OTP generation, hashing, and verification for email/phone verification.

Kept separate from password hashing on purpose: OTP codes are short-lived
(10 min), single-use, attempt-capped 6-digit numbers, not long-term
secrets — a fast keyed hash (HMAC-SHA256 with a server-side pepper) is
enough, since the attempt cap in verify_otp() is what actually stops
brute-forcing, not the hash's own computational cost the way it needs to
for a password.
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from app.config.db import otp_verifications_col

logger = logging.getLogger("app.otp")

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
MAX_ATTEMPTS = 5
# Once a code is verified, the proof of that (see verify_otp()'s "verified"
# branch and consume_verification_proof() below) stays valid for this long
# — long enough to finish filling out the rest of a signup form, short
# enough that a verified-but-abandoned identifier doesn't stay provable
# indefinitely.
VERIFICATION_PROOF_MINUTES = 15

# TODO: this project's other secrets (SMTP_*, MONGO_URI, etc.) live in
# app/config/settings.py — move OTP_PEPPER there alongside them once
# settings.py is available, for consistency. Reading directly from the
# environment here for now so this module doesn't depend on a file whose
# current contents weren't available when this was written.
_OTP_PEPPER = os.environ.get("OTP_PEPPER")
if not _OTP_PEPPER:
    logger.warning(
        "OTP_PEPPER not set in environment — using an insecure default. "
        "Set OTP_PEPPER before deploying to anything but local dev."
    )
    _OTP_PEPPER = "dev-insecure-otp-pepper-change-me"


def _hash_code(code: str) -> str:
    return hmac.new(_OTP_PEPPER.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_and_store_otp(*, identifier: str, purpose: str) -> str:
    """identifier: the email or phone being verified (already validated/
    normalized by OtpSendRequest). purpose: 'email_verify' or
    'phone_verify'. Returns the plaintext code — the caller is responsible
    for sending it; nothing else ever sees the plaintext again. A second
    send for the same (identifier, purpose) overwrites the first (upsert),
    so only the most recently sent code is ever valid."""
    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    now = datetime.now(timezone.utc)
    otp_verifications_col.update_one(
        {"identifier": identifier, "purpose": purpose},
        {
            "$set": {
                "code_hash": _hash_code(code),
                "expires_at": now + timedelta(minutes=OTP_EXPIRY_MINUTES),
                "attempts": 0,
                "created_at": now,
                # Explicitly reset, not just left to default — without
                # this, a stale verified:True from an earlier (possibly
                # expired-and-abandoned) verification would survive this
                # upsert untouched, letting consume_verification_proof()
                # accept a proof for a code that was never actually
                # verified this time around.
                "verified": False,
            }
        },
        upsert=True,
    )
    return code


def verify_otp(*, identifier: str, purpose: str, submitted_code: str) -> tuple[bool, str]:
    """Returns (success, error_message) — error_message is "" on success."""
    doc = otp_verifications_col.find_one({"identifier": identifier, "purpose": purpose})
    if not doc:
        return False, "No verification code was requested for this contact detail."

    expires_at = doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        otp_verifications_col.delete_one({"_id": doc["_id"]})
        return False, "This code has expired. Please request a new one."

    if doc.get("verified"):
        # Already succeeded on a previous call within the still-valid
        # proof window (e.g. a double-submit) — treat as success again
        # rather than falling through to the attempt-count/hash checks
        # below, which don't apply to an already-verified record.
        return True, ""

    if doc["attempts"] >= MAX_ATTEMPTS:
        otp_verifications_col.delete_one({"_id": doc["_id"]})
        return False, "Too many incorrect attempts. Please request a new code."

    if not hmac.compare_digest(doc["code_hash"], _hash_code(submitted_code)):
        otp_verifications_col.update_one({"_id": doc["_id"]}, {"$inc": {"attempts": 1}})
        return False, "Incorrect code. Please try again."

    # Correct — instead of deleting immediately, mark it verified and give
    # it a fresh, short expiry. This becomes the proof
    # consume_verification_proof() (below) checks for at registration
    # time, rather than the code only being usable in the instant it's
    # entered.
    otp_verifications_col.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "verified": True,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_PROOF_MINUTES),
            }
        },
    )
    return True, ""


def consume_verification_proof(identifier: str, purpose: str) -> bool:
    """Called by POST /auth/register, not by /otp/verify itself. Atomically
    finds and deletes a verified, not-yet-expired proof left behind by
    verify_otp() above. Returns True if one existed (and is now consumed),
    False if this identifier was never verified or the proof has since
    expired. Consuming it — rather than just checking it — means a single
    successful verification can only unlock one registration, not be
    replayed if registration is attempted again later."""
    doc = otp_verifications_col.find_one_and_delete(
        {
            "identifier": identifier,
            "purpose": purpose,
            "verified": True,
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }
    )
    return doc is not None