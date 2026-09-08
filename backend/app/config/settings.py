import os
from dotenv import load_dotenv, find_dotenv

# Prefer an explicit .env file if present (searches parent directories),
# so running uvicorn from the repository root still picks up backend/.env.
# Prefer an explicit backend/.env file when present (handles running
# `uvicorn` from the repository root). Otherwise fall back to the usual
# dotenv discovery logic.
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
backend_env = os.path.join(base_dir, ".env")
if os.path.exists(backend_env):
    load_dotenv(backend_env)
else:
    env_path = find_dotenv()
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "maapsetu")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Legacy name kept so nothing importing JWT_EXPIRES_MINUTES breaks; now equals
# the short-lived access token expiry (was 7 days — that's too long-lived to
# be a "short-lived access token", so it's been folded into ACCESS_TOKEN_*).
ACCESS_TOKEN_EXPIRES_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
JWT_EXPIRES_MINUTES = ACCESS_TOKEN_EXPIRES_MINUTES

# Refresh tokens are long-lived, random (not JWTs), stored hashed in Mongo,
# and rotated on every use — see utils/security.py + config/db.py.
REFRESH_TOKEN_EXPIRES_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "7"))
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")

# Cookie flags for the refresh-token cookie. COOKIE_SECURE should be True in
# any real deployment (HTTPS) — default False only so local http://localhost
# dev doesn't silently drop the cookie.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "strict")

# Failed-login lockout (Section 1: account lockout / exponential backoff).
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_BASE_MINUTES = int(os.getenv("LOGIN_LOCKOUT_BASE_MINUTES", "1"))

# Max request body size (bytes) — mirrors the checklist's body-parser limit.
MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(2 * 1024 * 1024)))  # 2MB

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# Public URL of the verify-page app (Aritra + Anushka). The QR code on every
# certificate points here + "/{cert_id}". Set this in .env once verify-page
# is deployed — falls back to localhost for local dev against `next dev`.
FRONTEND_VERIFY_URL = os.getenv("FRONTEND_VERIFY_URL", "http://localhost:3001/verify")


class _Settings:
    """
    Object-style access to the same values above, e.g. settings.CLOUDINARY_API_KEY.
    Exists because qr_generator.py and upload_to_cloudinary.py (Kiran) import
    `settings` as an object rather than the flat module-level names — both
    styles now work, so nobody has to change their existing import.
    """
    MONGO_URI = MONGO_URI
    DB_NAME = DB_NAME
    JWT_SECRET = JWT_SECRET
    JWT_ALGORITHM = JWT_ALGORITHM
    JWT_EXPIRES_MINUTES = JWT_EXPIRES_MINUTES
    ACCESS_TOKEN_EXPIRES_MINUTES = ACCESS_TOKEN_EXPIRES_MINUTES
    REFRESH_TOKEN_EXPIRES_DAYS = REFRESH_TOKEN_EXPIRES_DAYS
    REFRESH_COOKIE_NAME = REFRESH_COOKIE_NAME
    COOKIE_SECURE = COOKIE_SECURE
    COOKIE_SAMESITE = COOKIE_SAMESITE
    LOGIN_MAX_ATTEMPTS = LOGIN_MAX_ATTEMPTS
    LOGIN_LOCKOUT_BASE_MINUTES = LOGIN_LOCKOUT_BASE_MINUTES
    MAX_REQUEST_BODY_BYTES = MAX_REQUEST_BODY_BYTES
    CLOUDINARY_CLOUD_NAME = CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY = CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET = CLOUDINARY_API_SECRET
    FRONTEND_VERIFY_URL = FRONTEND_VERIFY_URL


settings = _Settings()
