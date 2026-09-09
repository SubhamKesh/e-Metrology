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

# Deployment environment. Defaults to "development" so local dev / CI (which
# never sets this) keep today's lenient behaviour. Set ENVIRONMENT=production
# in the real deploy target (Render/Railway/etc) to turn on the production
# guards below (JWT_SECRET check, /__dev/* routes disabled).
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Values that must never be used as JWT_SECRET in production — either the
# dev fallback below, or the placeholder that ships in .env.example.
_INSECURE_JWT_SECRETS = {"", "dev_secret_change_me", "change_this_to_a_long_random_string"}

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

if IS_PRODUCTION and (JWT_SECRET in _INSECURE_JWT_SECRETS or len(JWT_SECRET) < 32):
    # Fail loudly and immediately at import time (i.e. before uvicorn even
    # starts accepting connections) rather than silently signing tokens with
    # a guessable/default secret. This is the guard called out as missing in
    # the security-hardening status doc.
    raise RuntimeError(
        "Refusing to start with ENVIRONMENT=production and an insecure "
        "JWT_SECRET. Set a long (32+ char), random JWT_SECRET in the "
        "production environment's env vars — do not use the .env.example "
        "placeholder or the local-dev default."
    )
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

if IS_PRODUCTION and not COOKIE_SECURE:
    raise RuntimeError(
        "Refusing to start with ENVIRONMENT=production and COOKIE_SECURE "
        "unset/false — the refresh-token cookie would be sent over plain "
        "HTTP. Set COOKIE_SECURE=true once the app is served over HTTPS."
    )

# CORS: comma-separated list of allowed origins, e.g.
#   CORS_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
# Falls back to the Vite dev server origin so local dev keeps working
# untouched. In production this MUST be set to the real deployed frontend
# origin(s) — never "*", since allow_credentials=True is also set (browsers
# reject "*" + credentials anyway, but a stray "*" here would still be a bug).
_default_cors_origins = "http://localhost:5173"
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", _default_cors_origins).split(",")
    if origin.strip()
]

if IS_PRODUCTION and (
    not CORS_ALLOWED_ORIGINS
    or any(o in ("*", "http://localhost:5173") for o in CORS_ALLOWED_ORIGINS)
):
    raise RuntimeError(
        "Refusing to start with ENVIRONMENT=production and no real "
        "CORS_ALLOWED_ORIGINS configured. Set CORS_ALLOWED_ORIGINS to your "
        "deployed frontend's origin(s) (comma-separated), e.g. "
        "CORS_ALLOWED_ORIGINS=https://your-frontend.example.com"
    )

# Redis is optional. When set, the DDoS-protection middleware (and, in the
# future, anything else that needs cross-worker/cross-instance shared state)
# uses Redis instead of an in-process dict, so state is correct across
# uvicorn's --workers N and across multiple deployed instances. When unset,
# everything falls back to today's in-memory behaviour (fine for a single
# worker / local dev, NOT correct for --workers > 1 or multiple containers).
REDIS_URL = os.getenv("REDIS_URL", "").strip()

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

# Where an emailed "your account was created" message should send officers
# to sign in — the main app's /login page, not the verify-page app above.
FRONTEND_LOGIN_URL = os.getenv("FRONTEND_LOGIN_URL", "http://localhost:5173/login")

# SMTP, used only to email an admin-created officer their one-time temp
# password (see app/services/mailer.py). All optional: if SMTP_HOST/FROM
# aren't set, the mailer logs a warning and no-ops instead of failing the
# request — the admin still sees the temp password once in the API
# response as a fallback, so account creation is never blocked on email
# being configured.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


class _Settings:
    """
    Object-style access to the same values above, e.g. settings.CLOUDINARY_API_KEY.
    Exists because qr_generator.py and upload_to_cloudinary.py (Kiran) import
    `settings` as an object rather than the flat module-level names — both
    styles now work, so nobody has to change their existing import.
    """
    MONGO_URI = MONGO_URI
    DB_NAME = DB_NAME
    ENVIRONMENT = ENVIRONMENT
    IS_PRODUCTION = IS_PRODUCTION
    JWT_SECRET = JWT_SECRET
    JWT_ALGORITHM = JWT_ALGORITHM
    JWT_EXPIRES_MINUTES = JWT_EXPIRES_MINUTES
    ACCESS_TOKEN_EXPIRES_MINUTES = ACCESS_TOKEN_EXPIRES_MINUTES
    REFRESH_TOKEN_EXPIRES_DAYS = REFRESH_TOKEN_EXPIRES_DAYS
    REFRESH_COOKIE_NAME = REFRESH_COOKIE_NAME
    COOKIE_SECURE = COOKIE_SECURE
    COOKIE_SAMESITE = COOKIE_SAMESITE
    CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS
    REDIS_URL = REDIS_URL
    LOGIN_MAX_ATTEMPTS = LOGIN_MAX_ATTEMPTS
    LOGIN_LOCKOUT_BASE_MINUTES = LOGIN_LOCKOUT_BASE_MINUTES
    MAX_REQUEST_BODY_BYTES = MAX_REQUEST_BODY_BYTES
    CLOUDINARY_CLOUD_NAME = CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY = CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET = CLOUDINARY_API_SECRET
    FRONTEND_VERIFY_URL = FRONTEND_VERIFY_URL
    FRONTEND_LOGIN_URL = FRONTEND_LOGIN_URL
    SMTP_HOST = SMTP_HOST
    SMTP_PORT = SMTP_PORT
    SMTP_USER = SMTP_USER
    SMTP_PASSWORD = SMTP_PASSWORD
    SMTP_FROM = SMTP_FROM
    SMTP_USE_TLS = SMTP_USE_TLS


settings = _Settings()
