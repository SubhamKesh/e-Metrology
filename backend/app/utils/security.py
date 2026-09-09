import secrets
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config.settings import (
    JWT_SECRET,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRES_MINUTES,
    REFRESH_TOKEN_EXPIRES_DAYS,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def generate_temp_password() -> str:
    """Random, URL-safe temp password for admin-provisioned officer accounts.
    Shown to the admin exactly once at creation time; only its bcrypt hash
    is ever stored. The officer is forced to change it on first login."""
    return secrets.token_urlsafe(9)  # ~12 chars, enough entropy for a one-time credential


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- Access tokens (short-lived JWT) -----------------------------------
#
# `tv` (token_version) is copied from the user document at issue time and
# re-checked on every request in middleware/auth.py. Bumping a user's
# token_version (e.g. on logout-all, password change, or admin-forced
# revocation) instantly invalidates every access token already issued for
# that user, without needing a Redis blacklist — the check happens against
# Mongo, which we're already querying per-request anyway.

def create_access_token(user_id: str, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
    payload = {"sub": user_id, "tv": token_version, "exp": expire, "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Returns the decoded payload ({sub, tv, exp}), or raises jwt exceptions."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


# Back-compat shim: routers/callers that only need the user id can keep
# calling decode_token(...) -> str, same as before this change.
def decode_token(token: str) -> str:
    return decode_access_token(token)["sub"]


def create_token(user_id: str, token_version: int = 0) -> str:
    """Back-compat alias for create_access_token."""
    return create_access_token(user_id, token_version)


# --- Refresh tokens (opaque random string, stored hashed in Mongo) -----
#
# Deliberately NOT a JWT: a refresh token's only job is "look this up in
# refresh_tokens_col and see if it's still valid", so there's nothing to
# gain from it being self-describing, and every issued token needs to be
# individually revocable/rotatable — which a stateless JWT can't do
# without the Redis blacklist the checklist calls for. We store only a
# SHA-256 hash of the token in the DB, so a DB read/backup leak alone
# doesn't hand out usable tokens.

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)
