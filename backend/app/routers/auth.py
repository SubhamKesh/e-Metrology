from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pymongo.errors import DuplicateKeyError

from app.config.db import users_col, refresh_tokens_col
from app.config.constants import ROLES
from app.config.settings import (
    REFRESH_COOKIE_NAME,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_LOCKOUT_BASE_MINUTES,
)
from app.models.user import UserRegister, UserLogin, UserOut, TokenResponse
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from app.middleware.auth import get_current_user

try:
    from app.rate_limit import limiter, RATE_LIMIT_AUTH
except ImportError:  # pragma: no cover - slowapi not installed yet
    limiter = None
    RATE_LIMIT_AUTH = None

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
    )


def _issue_tokens(response: Response, user_doc: dict) -> str:
    """Creates a short-lived access token + a rotated refresh token cookie.
    Returns the access token (callers put it in the JSON body)."""
    access_token = create_access_token(str(user_doc["_id"]), user_doc.get("token_version", 0))

    raw_refresh = generate_refresh_token()
    refresh_tokens_col.insert_one(
        {
            "token_hash": hash_refresh_token(raw_refresh),
            "user_id": str(user_doc["_id"]),
            "expires_at": refresh_token_expiry(),
            "revoked": False,
            "created_at": datetime.now(timezone.utc),
        }
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/v1/auth",
    )
    return access_token


def _record_failed_login(user_doc: dict) -> None:
    attempts = user_doc.get("failed_login_attempts", 0) + 1
    update = {"$set": {"failed_login_attempts": attempts}}
    # Exponential backoff: 1 min, 2 min, 4 min, 8 min... once past the
    # attempt threshold, instead of a flat lockout window.
    if attempts >= LOGIN_MAX_ATTEMPTS:
        backoff_minutes = LOGIN_LOCKOUT_BASE_MINUTES * (2 ** (attempts - LOGIN_MAX_ATTEMPTS))
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
        update["$set"]["locked_until"] = locked_until
    users_col.update_one({"_id": user_doc["_id"]}, update)


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
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")

    if payload.role == "admin":
        # The minister / department-head account is provisioned exclusively
        # by seed_super_admin.py, never through open self-registration.
        raise HTTPException(status_code=403, detail="This role cannot self-register")

    # Owners can use their account right away. lmo/gatc accounts represent
    # real government officers, so they sit in "pending" until the admin
    # (minister) approves them — see /admin/users/{id}/approve below.
    status = "active" if payload.role == "owner" else "pending"

    doc = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
        "role": payload.role,
        "status": status,
        "org_type": payload.org_type,
        "org_name": payload.org_name,
        "contact": payload.contact,
        "token_version": 0,
        "failed_login_attempts": 0,
    }

    try:
        result = users_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email already registered")

    doc["_id"] = result.inserted_id

    if status == "pending":
        # No token for a pending account — they can't do anything yet.
        # The frontend should show "awaiting admin approval" rather than
        # logging them straight in.
        return TokenResponse(user=to_user_out(doc), token="")

    token = _issue_tokens(response, doc)
    return TokenResponse(user=to_user_out(doc), token=token)


@router.post("/login", response_model=TokenResponse)
@_rate_limit
def login(payload: UserLogin, request: Request, response: Response):
    user = users_col.find_one({"email": payload.email.lower()})

    # Same "Invalid email or password" message whether the email doesn't
    # exist or the password is wrong — don't leak which one it was.
    invalid_creds = HTTPException(status_code=401, detail="Invalid email or password")

    if not user:
        raise invalid_creds

    locked_until = user.get("locked_until")
    if locked_until and locked_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
        )

    if not verify_password(payload.password, user["password"]):
        _record_failed_login(user)
        raise invalid_creds

    user_status = user.get("status", "active")  # see to_user_out() for why the fallback
    if user_status == "pending":
        raise HTTPException(status_code=403, detail="Your account is awaiting admin approval")
    if user_status == "rejected":
        raise HTTPException(status_code=403, detail="Your account registration was not approved")

    _clear_login_attempts(user["_id"])
    token = _issue_tokens(response, user)
    return TokenResponse(user=to_user_out(user), token=token)


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
        raise HTTPException(status_code=401, detail="Refresh token is invalid or revoked")

    expires_at = stored["expires_at"]
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    user = users_col.find_one({"_id": ObjectId(stored["user_id"])})
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    # Rotation: this refresh token is now spent, regardless of outcome below.
    refresh_tokens_col.update_one({"_id": stored["_id"]}, {"$set": {"revoked": True}})

    token = _issue_tokens(response, user)
    return TokenResponse(user=to_user_out(user), token=token)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    """Revokes just the current refresh token (this device/session)."""
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        refresh_tokens_col.update_one(
            {"token_hash": hash_refresh_token(raw_refresh)},
            {"$set": {"revoked": True}},
        )
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(response: Response, current_user: dict = Depends(get_current_user)):
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
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    return to_user_out(current_user)
