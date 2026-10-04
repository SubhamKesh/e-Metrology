from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config.db import users_col, refresh_tokens_col
from app.config.constants import ROLES
from app.config.settings import (
    REFRESH_COOKIE_NAME,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_LOCKOUT_BASE_MINUTES,
    REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS,
    PASSWORD_RESET_COOLDOWN_SECONDS,
    SELF_SERVICE_AUTH_ROLES,
    MFA_REQUIRED_ROLES,
    MFA_ISSUER,
)
from app.models.user import (
    UserRegister,
    UserLogin,
    UserOut,
    TokenResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    LoginResponse,
    MfaTokenRequest,
    MfaCodeRequest,
    MfaSetupResponse,
)
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    create_mfa_token,
    decode_mfa_token,
)
from app.utils.totp import generate_secret, verify_totp, provisioning_uri
from app.utils.mfa import (
    encrypt_secret,
    decrypt_secret,
    generate_recovery_codes,
    hash_recovery_code,
    qr_data_uri,
)
from app.middleware.auth import get_current_user
from app.services.audit import log_event
from app.services.email_templates import render_otp
from app.services.mailer import noreply_sender, send_email, send_password_changed_notice
from app.services.otp import (
    OTP_EXPIRY_MINUTES,
    consume_verification_proof,
    generate_and_store_otp,
    otp_sent_within,
    verify_and_consume_otp,
)

try:
    from app.rate_limit import limiter, RATE_LIMIT_AUTH
except ImportError:  # pragma: no cover - slowapi not installed yet
    limiter = None
    RATE_LIMIT_AUTH = None

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# OTP purpose for password resets. Kept separate from the signup
# "email_verify" purpose so the two flows can never satisfy each other.
PASSWORD_RESET_PURPOSE = "password_reset"


def to_user_out(user_doc: dict) -> UserOut:
    return UserOut(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        email=user_doc["email"],
        role=user_doc["role"],
        # Older documents created before the approval-gate feature won't
        # have a status field at all — treat those as active so existing
        # accounts don't get silently locked out by this change.
        status=user_doc.get("status", "active"),
        org_type=user_doc.get("org_type"),
        org_name=user_doc.get("org_name"),
        contact=user_doc.get("contact"),
        is_email_verified=user_doc.get("is_email_verified", False),
        is_phone_verified=user_doc.get("is_phone_verified", False),
        must_change_password=user_doc.get("must_change_password", False),
        mfa_enabled=bool(user_doc.get("mfa_enabled", False)),
    )


def _issue_tokens(
    response: Response, user_doc: dict, remember_me: bool = False, mfa_verified: bool = False
) -> tuple[str, bool]:
    """Creates a short-lived access token + a rotated refresh token cookie.
    Returns (access_token, remember_me_honoured): callers put the token in the
    JSON body, and report whether remember-me was actually applied.

    remember_me=False -> the cookie is a browser-session cookie (gone when the
    browser closes) and the stored token lives REFRESH_TOKEN_EXPIRES_DAYS.
    remember_me=True  -> the cookie is persistent and, together with the
    stored token, lives REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS. The choice is
    saved on the token record so /refresh can carry it forward on rotation.

    mfa_verified=True records that the second step was completed for this
    session. For roles in MFA_REQUIRED_ROLES, /refresh refuses any refresh
    token without it — so a session can never be renewed into existence
    from a password alone (this also retires refresh tokens that were issued
    before two-step verification existed)."""
    access_token = create_access_token(str(user_doc["_id"]), user_doc.get("token_version", 0))

    # Server-side rule, regardless of what the client sent: only roles in
    # SELF_SERVICE_AUTH_ROLES (owners) can have a long-lived session.
    remember_me = remember_me and user_doc.get("role") in SELF_SERVICE_AUTH_ROLES

    raw_refresh = generate_refresh_token()
    refresh_tokens_col.insert_one(
        {
            "token_hash": hash_refresh_token(raw_refresh),
            "user_id": str(user_doc["_id"]),
            "expires_at": refresh_token_expiry(REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS if remember_me else None),
            "revoked": False,
            "remember_me": remember_me,
            "mfa_verified": mfa_verified,
            "created_at": datetime.now(timezone.utc),
        }
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        # No max_age => session cookie. With it => survives browser restarts.
        max_age=REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60 if remember_me else None,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/v1/auth",
    )
    return access_token, remember_me


def _record_failed_login(user_doc: dict) -> bool:
    """Counts a failed attempt. Returns True if this attempt locked the account."""
    attempts = user_doc.get("failed_login_attempts", 0) + 1
    update = {"$set": {"failed_login_attempts": attempts}}
    # Exponential backoff: 1 min, 2 min, 4 min, 8 min... once past the
    # attempt threshold, instead of a flat lockout window.
    if attempts >= LOGIN_MAX_ATTEMPTS:
        backoff_minutes = LOGIN_LOCKOUT_BASE_MINUTES * (2 ** (attempts - LOGIN_MAX_ATTEMPTS))
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
        update["$set"]["locked_until"] = locked_until
    users_col.update_one({"_id": user_doc["_id"]}, update)
    return attempts >= LOGIN_MAX_ATTEMPTS


def _clear_login_attempts(user_id) -> None:
    users_col.update_one(
        {"_id": user_id},
        {"$set": {"failed_login_attempts": 0}, "$unset": {"locked_until": ""}},
    )


def _rate_limit(fn):
    """Applies slowapi's limiter if it's installed; no-ops otherwise so the
    app still runs before `pip install -r requirements.txt` picks up
    slowapi. See app/rate_limit.py for the actual limit configuration."""
    if limiter is None or RATE_LIMIT_AUTH is None:
        return fn
    return limiter.limit(RATE_LIMIT_AUTH)(fn)


@router.post("/register", response_model=TokenResponse, status_code=201)
@_rate_limit
def register(payload: UserRegister, request: Request, response: Response):
    reg_email = payload.email.strip().lower()

    if payload.role not in ROLES:
        log_event("account_registration_failed", outcome="failure", request=request, email=reg_email, detail="invalid_role")
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")

    if payload.role != "owner":
        # Someone is trying to self-register as an officer/admin: worth a record.
        log_event(
            "account_registration_failed",
            outcome="blocked",
            request=request,
            email=reg_email,
            detail=f"role_not_allowed:{payload.role}",
        )
        # Open self-registration only exists for owner (business/user)
        # accounts. lmo/gatc are real government officer roles and are
        # invite-only: an admin creates them directly via
        # POST /admin/users/create-officer, with a temp password the admin
        # shares out of band. admin itself is seed-only. Either way, this
        # endpoint has nothing to offer a non-owner role.
        raise HTTPException(
            status_code=403,
            detail="Officer accounts are created by an administrator, not self-registered",
        )

    # Account creation requires a verified email — see POST
    # /api/v1/otp/send + /verify, which a registering owner calls before
    # this endpoint. consume_verification_proof() atomically finds-and-
    # deletes a still-valid proof, so one verification can only unlock
    # one registration. strip().lower() matches how OtpSendRequest
    # normalizes the identifier, so the proof lookup key lines up.
    email = payload.email.strip().lower()
    if not consume_verification_proof(email, "email_verify"):
        log_event("account_registration_failed", outcome="failure", request=request, email=email, detail="email_not_verified")
        raise HTTPException(
            status_code=400,
            detail="Please verify your email before creating an account.",
        )

    doc = {
        "name": payload.name,
        "email": email,
        "password": hash_password(payload.password),
        "role": "owner",
        "status": "active",
        "org_type": payload.org_type,
        "org_name": payload.org_name,
        "contact": payload.contact,
        "is_email_verified": True,
        "is_phone_verified": False,
        "token_version": 0,
        "failed_login_attempts": 0,
        "must_change_password": False,
    }

    try:
        result = users_col.insert_one(doc)
    except DuplicateKeyError:
        # Known trade-off: the verification proof above is already
        # consumed by this point, even though account creation itself
        # failed here. A person hitting this (an already-registered email)
        # would need to go verify again before retrying — acceptable
        # since verification is meant to happen immediately before
        # registration, not stockpiled for later.
        log_event("account_registration_failed", outcome="failure", request=request, email=email, detail="email_exists")
        raise HTTPException(status_code=409, detail="Email already registered")

    doc["_id"] = result.inserted_id

    log_event(
        "account_registered",
        outcome="success",
        request=request,
        email=email,
        user_id=str(result.inserted_id),
        role="owner",
        detail="auto_login",
    )
    token, _ = _issue_tokens(response, doc)
    return TokenResponse(user=to_user_out(doc), token=token)


@router.post("/login", response_model=LoginResponse)
@_rate_limit
def login(payload: UserLogin, request: Request, response: Response):
    user = users_col.find_one({"email": payload.email.lower()})

    # Same "Invalid email or password" message whether the email doesn't
    # exist or the password is wrong — don't leak which one it was.
    invalid_creds = HTTPException(status_code=401, detail="Invalid email or password")

    if not user:
        log_event("login_failed", outcome="failure", request=request, email=payload.email.lower(), detail="unknown_email")
        raise invalid_creds

    who = {"email": user["email"], "user_id": str(user["_id"]), "role": user.get("role")}

    locked_until = user.get("locked_until")
    if locked_until and locked_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        log_event("login_blocked", outcome="blocked", request=request, detail="account_locked", **who)
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
        )

    if not verify_password(payload.password, user["password"]):
        locked_now = _record_failed_login(user)
        log_event(
            "login_failed",
            outcome="failure",
            request=request,
            detail="wrong_password_account_locked" if locked_now else "wrong_password",
            **who,
        )
        raise invalid_creds

    user_status = user.get("status", "active")  # see to_user_out() for why the fallback
    if user_status == "pending":
        log_event("login_blocked", outcome="blocked", request=request, detail="account_pending", **who)
        raise HTTPException(status_code=403, detail="Your account is awaiting admin approval")
    if user_status == "rejected":
        log_event("login_blocked", outcome="blocked", request=request, detail="account_rejected", **who)
        raise HTTPException(status_code=403, detail="Your account registration was not approved")

    # Officer and admin accounts: the password is only step one. Nothing
    # that grants access (no access token, no refresh cookie, no user data)
    # is released until the second step — a code from the authenticator app —
    # passes in /auth/mfa/verify (or, for an account with no authenticator
    # yet, until one is enrolled in /auth/mfa/confirm-setup). The failed-
    # attempt counter is deliberately NOT cleared here: it is cleared only
    # after the second step succeeds, so an attacker who knows the password
    # can't reset the counter with it and keep guessing codes.
    if user.get("role") in MFA_REQUIRED_ROLES:
        needs_setup = not user.get("mfa_enabled")
        log_event(
            "login_password_verified",
            outcome="success",
            request=request,
            detail="mfa_setup_required" if needs_setup else "mfa_required",
            **who,
        )
        return LoginResponse(
            mfa_required=not needs_setup,
            mfa_setup_required=needs_setup,
            mfa_token=create_mfa_token(str(user["_id"]), user.get("token_version", 0), "setup" if needs_setup else "verify"),
        )

    _clear_login_attempts(user["_id"])
    token, remembered = _issue_tokens(response, user, remember_me=payload.remember_me)
    log_event("login_success", outcome="success", request=request, detail="remember_me" if remembered else None, **who)
    return LoginResponse(user=to_user_out(user), token=token, remember_me=remembered)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response):
    """Exchanges a valid refresh-token cookie for a new access token, and
    rotates the refresh token (old one is revoked, a new one is issued) so a
    stolen-but-unused refresh token becomes useless the next time the real
    owner refreshes."""
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    token_hash = hash_refresh_token(raw_refresh)
    stored = refresh_tokens_col.find_one({"token_hash": token_hash})

    if not stored or stored.get("revoked"):
        if stored:
            # A token that was already used/revoked is being presented again:
            # either a stale tab racing a refresh, or a stolen copy. Worth a record.
            log_event(
                "refresh_rejected",
                outcome="blocked",
                request=request,
                user_id=stored.get("user_id"),
                detail="revoked_token_presented",
            )
        raise HTTPException(status_code=401, detail="Refresh token is invalid or revoked")

    expires_at = stored["expires_at"]
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    user = users_col.find_one({"_id": ObjectId(stored["user_id"])})
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    # A suspended / not-approved account can't keep renewing a session.
    if user.get("status", "active") != "active":
        log_event("refresh_rejected", outcome="blocked", request=request, user_id=stored["user_id"], detail="account_not_active")
        raise HTTPException(status_code=401, detail="Refresh token is invalid or revoked")

    # Officer/admin sessions must have passed the second step. Refresh tokens
    # without that mark (e.g. issued before two-step verification existed)
    # are refused, which forces a fresh sign-in through /auth/login + MFA.
    if user.get("role") in MFA_REQUIRED_ROLES and not stored.get("mfa_verified"):
        log_event(
            "refresh_rejected",
            outcome="blocked",
            request=request,
            email=user["email"],
            user_id=stored["user_id"],
            role=user["role"],
            detail="mfa_not_verified",
        )
        raise HTTPException(status_code=401, detail="Please sign in again.")

    # Rotation: this refresh token is now spent, regardless of outcome below.
    refresh_tokens_col.update_one({"_id": stored["_id"]}, {"$set": {"revoked": True}})

    # Rotation keeps the user's original "remember me" choice: a remembered
    # session stays remembered (and its 30-day window slides forward), a
    # plain session stays a session cookie.
    token, remembered = _issue_tokens(
        response,
        user,
        remember_me=bool(stored.get("remember_me", False)),
        mfa_verified=bool(stored.get("mfa_verified", False)),
    )
    return TokenResponse(user=to_user_out(user), token=token, remember_me=remembered)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    """Revokes just the current refresh token (this device/session)."""
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        token_hash = hash_refresh_token(raw_refresh)
        stored = refresh_tokens_col.find_one({"token_hash": token_hash})
        refresh_tokens_col.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked": True}},
        )
        if stored:
            owner = users_col.find_one({"_id": ObjectId(stored["user_id"])})
            log_event(
                "logout",
                outcome="success",
                request=request,
                email=owner["email"] if owner else None,
                user_id=stored["user_id"],
                role=owner.get("role") if owner else None,
            )
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
    """Revokes every refresh token AND every already-issued access token for
    this user (via token_version bump) — e.g. 'log out everywhere' after a
    suspected compromise."""
    users_col.update_one(
        {"_id": current_user["_id"]},
        {"$inc": {"token_version": 1}},
    )
    refresh_tokens_col.update_many(
        {"user_id": str(current_user["_id"]), "revoked": False},
        {"$set": {"revoked": True}},
    )
    log_event(
        "logout_all",
        outcome="success",
        request=request,
        email=current_user["email"],
        user_id=str(current_user["_id"]),
        role=current_user["role"],
    )
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    return to_user_out(current_user)


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Used both for a voluntary password change and for the forced
    change an admin-created officer must do on first login (see
    must_change_password on UserOut).

    A password change signs the account out of EVERY session — other
    browsers, other devices, and anyone who had the old password or a stolen
    session — and then issues a fresh session for the device that just made
    the change (new access token in the body, new refresh cookie), so the
    person changing their password isn't logged out of their own screen."""
    who = {"email": current_user["email"], "user_id": str(current_user["_id"]), "role": current_user["role"]}

    if not verify_password(payload.current_password, current_user["password"]):
        log_event("password_change_failed", outcome="failure", request=request, detail="wrong_current_password", **who)
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if payload.new_password == payload.current_password:
        log_event("password_change_failed", outcome="failure", request=request, detail="same_as_current", **who)
        raise HTTPException(status_code=400, detail="New password must be different from your current password.")

    # Carry this device's "remember me" choice over to its replacement session.
    remember_me = False
    mfa_verified = False
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        current_session = refresh_tokens_col.find_one({"token_hash": hash_refresh_token(raw_refresh)})
        if current_session and current_session.get("user_id") == str(current_user["_id"]):
            remember_me = bool(current_session.get("remember_me", False))
            mfa_verified = bool(current_session.get("mfa_verified", False))

    updated_user = users_col.find_one_and_update(
        {"_id": current_user["_id"]},
        {
            "$set": {"password": hash_password(payload.new_password), "must_change_password": False},
            # Kills every access token issued so far (see middleware/auth.py).
            "$inc": {"token_version": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    refresh_tokens_col.update_many(
        {"user_id": str(current_user["_id"]), "revoked": False},
        {"$set": {"revoked": True}},
    )

    # Fresh session for this device, built from the post-update document so
    # the new access token carries the new token_version.
    token, remembered = _issue_tokens(response, updated_user, remember_me=remember_me, mfa_verified=mfa_verified)

    log_event("password_changed", outcome="success", request=request, detail="other_sessions_revoked", **who)
    background_tasks.add_task(send_password_changed_notice, to=updated_user["email"], name=updated_user["name"])
    return ChangePasswordResponse(**to_user_out(updated_user).model_dump(), token=token, remember_me=remembered)


@router.post("/forgot-password")
@_rate_limit
def forgot_password(payload: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks):
    """Emails a 6-digit reset code if a self-service account exists for this
    email.

    Always answers the same {"sent": true}, whether or not the account
    exists, whether or not the cooldown suppressed the email, and whether or
    not the account is an officer/admin (which cannot self-reset), so this
    endpoint can't be used to find out who has an account or what role they
    hold. The email itself is sent in a background task so response time
    doesn't give it away either. Every outcome is audit-logged."""
    email = payload.email
    generic = {"sent": True}

    user = users_col.find_one({"email": email})
    if not user:
        log_event("password_reset_requested", outcome="ignored", request=request, email=email, detail="no_account")
        return generic

    who = {"email": email, "user_id": str(user["_id"]), "role": user.get("role")}

    if user.get("role") not in SELF_SERVICE_AUTH_ROLES:
        log_event("password_reset_requested", outcome="blocked", request=request, detail="role_requires_admin_reset", **who)
        return generic

    if otp_sent_within(identifier=email, purpose=PASSWORD_RESET_PURPOSE, seconds=PASSWORD_RESET_COOLDOWN_SECONDS):
        log_event("password_reset_requested", outcome="ignored", request=request, detail="cooldown", **who)
        return generic

    code = generate_and_store_otp(identifier=email, purpose=PASSWORD_RESET_PURPOSE)
    subject, text, html = render_otp("password_reset", code, OTP_EXPIRY_MINUTES)
    background_tasks.add_task(
        send_email,
        to=email,
        subject=subject,
        body=text,
        html=html,
        sender=noreply_sender(),
    )
    log_event("password_reset_requested", outcome="success", request=request, detail="code_sent", **who)
    return generic


@router.post("/reset-password")
@_rate_limit
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Sets a new password using the code from /forgot-password.

    Every failure (wrong code, expired, too many attempts, unknown email,
    officer/admin account) returns the same message on purpose. On success
    the account's existing sessions are all revoked, any failed-login
    lockout is cleared, and a "your password was changed" email is sent."""
    email = payload.email
    failure = HTTPException(status_code=400, detail="Invalid or expired code. Please request a new one.")

    code_ok = verify_and_consume_otp(
        identifier=email,
        purpose=PASSWORD_RESET_PURPOSE,
        submitted_code=payload.code,
    )
    user = users_col.find_one({"email": email})

    if not code_ok:
        log_event(
            "password_reset_failed",
            outcome="failure",
            request=request,
            email=email,
            user_id=str(user["_id"]) if user else None,
            role=user.get("role") if user else None,
            detail="invalid_or_expired_code" if user else "no_account",
        )
        raise failure

    who = {"email": email, "user_id": str(user["_id"]) if user else None, "role": user.get("role") if user else None}

    # Defence in depth: even if a code somehow exists for an officer/admin
    # account, it can never be used to reset their password here.
    if not user or user.get("role") not in SELF_SERVICE_AUTH_ROLES:
        log_event("password_reset_failed", outcome="blocked", request=request, detail="role_requires_admin_reset", **who)
        raise failure

    users_col.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "password": hash_password(payload.new_password),
                "must_change_password": False,
                "failed_login_attempts": 0,
            },
            "$unset": {"locked_until": ""},
            # Invalidates every access token already issued (see
            # middleware/auth.py) — whoever had the old password, or a
            # stolen session, is signed out.
            "$inc": {"token_version": 1},
        },
    )
    refresh_tokens_col.update_many(
        {"user_id": str(user["_id"]), "revoked": False},
        {"$set": {"revoked": True}},
    )
    log_event("password_reset_completed", outcome="success", request=request, **who)
    background_tasks.add_task(send_password_changed_notice, to=email, name=user["name"])
    return {"reset": True}


# ============================================================================
# Two-step verification (TOTP authenticator app) for officer / admin accounts
# ============================================================================
#
# Flow (see /auth/login): password accepted -> `mfa_token` ->
#   * no authenticator yet: POST /auth/mfa/setup      (get secret + QR)
#                           POST /auth/mfa/confirm-setup (prove it works)
#                           -> recovery codes shown once, session starts
#   * authenticator set up: POST /auth/mfa/verify     (6-digit code, or a
#                           one-time recovery code) -> session starts
# Wrong codes feed the same failed-attempt counter / lockout as wrong
# passwords, and every outcome is audit-logged.

_SETUP_PENDING_MAX_AGE = timedelta(minutes=15)
_INVALID_SIGNIN = "Invalid sign-in session. Please sign in again."


def _who(user: dict) -> dict:
    return {"email": user["email"], "user_id": str(user["_id"]), "role": user.get("role")}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load_mfa_user(mfa_token: str, purpose: str, request: Request) -> dict:
    """Validates an mfa_token for `purpose` and returns the live user document.
    Rejects expired/forged/wrong-purpose tokens, tokens that predate a password
    change or revocation (token_version), non-MFA roles, inactive accounts, and
    locked accounts."""
    try:
        payload = decode_mfa_token(mfa_token, purpose)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Your sign-in session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail=_INVALID_SIGNIN)

    try:
        user = users_col.find_one({"_id": ObjectId(payload["sub"])})
    except Exception:
        user = None

    if (
        not user
        or user.get("token_version", 0) != payload.get("tv", 0)
        or user.get("role") not in MFA_REQUIRED_ROLES
        or user.get("status", "active") != "active"
    ):
        raise HTTPException(status_code=401, detail=_INVALID_SIGNIN)

    locked_until = user.get("locked_until")
    if locked_until and _aware(locked_until) > datetime.now(timezone.utc):
        log_event("mfa_blocked", outcome="blocked", request=request, detail="account_locked", **_who(user))
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
    return user


def _mfa_failure(request: Request, user: dict, detail: str) -> None:
    """Counts the failure (shared lockout with passwords), audit-logs it, and
    raises the same 401 for every kind of wrong code."""
    locked_now = _record_failed_login(user)
    log_event(
        "mfa_failed",
        outcome="failure",
        request=request,
        detail=f"{detail}_account_locked" if locked_now else detail,
        **_who(user),
    )
    raise HTTPException(status_code=401, detail="Invalid verification code. Check your authenticator app and try again.")


@router.post("/mfa/setup", response_model=MfaSetupResponse)
@_rate_limit
def mfa_setup(payload: MfaTokenRequest, request: Request):
    """Step 1 of enrolment: returns the secret + QR code to add the account to
    an authenticator app. Repeating the call within 15 minutes returns the SAME
    secret (so a double-click or a page reload never leaves the app and the
    server holding different secrets)."""
    user = _load_mfa_user(payload.mfa_token, "setup", request)
    if user.get("mfa_enabled"):
        raise HTTPException(status_code=400, detail="Two-step verification is already set up for this account.")

    now = datetime.now(timezone.utc)
    candidate = generate_secret()
    # Only write if there's no pending secret yet, or the old one is stale.
    users_col.update_one(
        {
            "_id": user["_id"],
            "$or": [
                {"mfa_pending_secret": {"$exists": False}},
                {"mfa_pending_at": {"$lt": now - _SETUP_PENDING_MAX_AGE}},
            ],
        },
        {"$set": {"mfa_pending_secret": encrypt_secret(candidate), "mfa_pending_at": now}},
    )
    fresh = users_col.find_one({"_id": user["_id"]})
    secret = decrypt_secret(fresh["mfa_pending_secret"]) if fresh.get("mfa_pending_secret") else None
    if secret is None:  # unreadable (encryption key changed): start over
        secret = candidate
        users_col.update_one(
            {"_id": user["_id"]},
            {"$set": {"mfa_pending_secret": encrypt_secret(secret), "mfa_pending_at": now}},
        )

    log_event("mfa_setup_started", outcome="success", request=request, **_who(user))
    uri = provisioning_uri(secret, user["email"], MFA_ISSUER)
    return MfaSetupResponse(secret=secret, otpauth_uri=uri, qr_data_uri=qr_data_uri(uri))


@router.post("/mfa/confirm-setup", response_model=LoginResponse)
@_rate_limit
def mfa_confirm_setup(payload: MfaCodeRequest, request: Request, response: Response):
    """Step 2 of enrolment: the user types the code their app now shows, which
    proves the secret was scanned correctly. Turns two-step verification on,
    returns one-time recovery codes (shown only now) and starts the session."""
    user = _load_mfa_user(payload.mfa_token, "setup", request)
    if user.get("mfa_enabled"):
        raise HTTPException(status_code=400, detail="Two-step verification is already set up for this account.")

    pending = user.get("mfa_pending_secret")
    pending_at = user.get("mfa_pending_at")
    secret = decrypt_secret(pending) if pending else None
    if not secret or not pending_at or datetime.now(timezone.utc) - _aware(pending_at) > _SETUP_PENDING_MAX_AGE:
        raise HTTPException(status_code=400, detail="Setup expired. Please reload the page to start again.")

    step = verify_totp(secret, payload.code.replace(" ", ""))
    if step is None:
        _mfa_failure(request, user, "setup_wrong_code")

    recovery_codes = generate_recovery_codes()
    result = users_col.update_one(
        {"_id": user["_id"], "mfa_enabled": {"$ne": True}},
        {
            "$set": {
                "mfa_enabled": True,
                "mfa_secret_enc": pending,
                "mfa_enabled_at": datetime.now(timezone.utc),
                "mfa_last_step": step,
                "mfa_recovery_hashes": [hash_recovery_code(c) for c in recovery_codes],
            },
            "$unset": {"mfa_pending_secret": "", "mfa_pending_at": ""},
        },
    )
    if result.modified_count != 1:  # a concurrent request enrolled first
        raise HTTPException(status_code=400, detail="Two-step verification is already set up for this account.")

    _clear_login_attempts(user["_id"])
    user["mfa_enabled"] = True
    token, _ = _issue_tokens(response, user, remember_me=False, mfa_verified=True)
    log_event("mfa_enabled", outcome="success", request=request, **_who(user))
    log_event("login_success", outcome="success", request=request, detail="mfa_setup", **_who(user))
    return LoginResponse(user=to_user_out(user), token=token, recovery_codes=recovery_codes)


@router.post("/mfa/verify", response_model=LoginResponse)
@_rate_limit
def mfa_verify(payload: MfaCodeRequest, request: Request, response: Response):
    """Second step of login: a 6-digit code from the authenticator app, or one
    of the one-time recovery codes. A code can only be used once (a TOTP time
    step that was already accepted is refused, even inside its 30-second
    window). On success the session starts."""
    user = _load_mfa_user(payload.mfa_token, "verify", request)
    if not user.get("mfa_enabled") or not user.get("mfa_secret_enc"):
        raise HTTPException(status_code=400, detail="Two-step verification isn't set up. Please sign in again.")

    code = payload.code.replace(" ", "")
    recovery_remaining = None

    if code.isascii() and code.isdigit() and len(code) == 6:
        secret = decrypt_secret(user["mfa_secret_enc"])
        if secret is None:
            log_event("mfa_failed", outcome="failure", request=request, detail="secret_undecryptable", **_who(user))
            raise HTTPException(
                status_code=503,
                detail="Two-step verification is temporarily unavailable. Contact an administrator.",
            )
        step = verify_totp(secret, code, last_step=user.get("mfa_last_step"))
        if step is None:
            _mfa_failure(request, user, "wrong_code")
        # Atomically claim this time step: of two simultaneous submissions of
        # the same code, only one can move mfa_last_step forward.
        claimed = users_col.update_one(
            {
                "_id": user["_id"],
                "$or": [{"mfa_last_step": {"$lt": step}}, {"mfa_last_step": {"$exists": False}}],
            },
            {"$set": {"mfa_last_step": step}},
        )
        if claimed.modified_count != 1:
            _mfa_failure(request, user, "replayed_code")
        method = "mfa_totp"
    else:
        hashed = hash_recovery_code(code)
        # Atomic one-time consume: the pull only matches while the code is unused.
        updated = users_col.find_one_and_update(
            {"_id": user["_id"], "mfa_recovery_hashes": hashed},
            {"$pull": {"mfa_recovery_hashes": hashed}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            _mfa_failure(request, user, "wrong_code")
        user = updated
        recovery_remaining = len(updated.get("mfa_recovery_hashes", []))
        method = "mfa_recovery_code"

    _clear_login_attempts(user["_id"])
    token, _ = _issue_tokens(response, user, remember_me=False, mfa_verified=True)
    log_event("login_success", outcome="success", request=request, detail=method, **_who(user))
    return LoginResponse(user=to_user_out(user), token=token, recovery_codes_remaining=recovery_remaining)
