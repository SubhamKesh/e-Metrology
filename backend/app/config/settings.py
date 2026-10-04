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

# "Remember me": when the user ticks it at login, the refresh token (and its
# cookie) lives this many days instead of being a browser-session cookie.
# Each refresh rotates the token and restarts this window (sliding expiry).
REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS = int(os.getenv("REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS", "30"))

# Roles that may use the self-service "forgot password" flow and the
# "Remember me" option. Officer (lmo/gatc) and admin accounts are
# deliberately excluded: a stolen or compromised mailbox must not be enough
# to take over a government account, and shared office computers must not
# keep officers signed in for weeks. Their passwords are reset by an
# administrator (officers) or by the operator running seed_super_admin.py
# (the super admin).
SELF_SERVICE_AUTH_ROLES = frozenset({"owner"})

# Two-step verification (TOTP authenticator app). Mandatory for these roles:
# after the password is accepted they must also present a code from their
# authenticator app (or a one-time recovery code) before any session exists.
MFA_REQUIRED_ROLES = frozenset({"lmo", "gatc", "admin"})
# Lifetime of the short "password accepted, second step pending" token.
MFA_TOKEN_EXPIRES_MINUTES = int(os.getenv("MFA_TOKEN_EXPIRES_MINUTES", "10"))
# Shown in the authenticator app next to the account.
MFA_ISSUER = os.getenv("MFA_ISSUER", "MaapSetu")
MFA_RECOVERY_CODE_COUNT = int(os.getenv("MFA_RECOVERY_CODE_COUNT", "8"))
# Key material for encrypting TOTP secrets at rest. Optional: when unset it is
# derived from JWT_SECRET (which production already requires to be strong).
# Set a dedicated value so that rotating JWT_SECRET later doesn't make every
# stored authenticator secret undecryptable.
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", "")

# How long audit-log records are kept (days) before MongoDB expires them.
AUDIT_LOG_RETENTION_DAYS = max(int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "365")), 180)

# Forgot-password: minimum gap between two reset emails for the same account,
# so the endpoint can't be used to mail-bomb someone's inbox.
PASSWORD_RESET_COOLDOWN_SECONDS = int(os.getenv("PASSWORD_RESET_COOLDOWN_SECONDS", "60"))

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

# MongoDB read preference for READ-HEAVY, staleness-tolerant endpoints only
# (reference data, public certificate verification, dashboards, the audit-log
# viewer). Everything that must read its own writes or enforce security —
# sign-in, token/user checks, lists a user just changed — always reads the
# primary regardless of this setting.
#   primary             (default) every read goes to the primary; correct for
#                       a single node or when you have no replicas to use
#   secondaryPreferred  use a secondary when one is available, else the primary
#                       (recommended with a replica set / Atlas cluster)
# Replica reads can lag the primary by a moment (usually well under a second).
# Don't also put readPreference in MONGO_URI: that would send EVERY read,
# including the security-critical ones, to secondaries.
MONGO_READ_PREFERENCE = os.getenv("MONGO_READ_PREFERENCE", "primary").strip() or "primary"
_ALLOWED_READ_PREFERENCES = ("primary", "primaryPreferred", "secondaryPreferred", "nearest")
if MONGO_READ_PREFERENCE not in _ALLOWED_READ_PREFERENCES:
    raise ValueError(
        f"MONGO_READ_PREFERENCE={MONGO_READ_PREFERENCE!r} is not supported; use one of {_ALLOWED_READ_PREFERENCES}. "
        "('secondary' is deliberately not offered: it fails outright when no secondary is available.)"
    )

# Signup OTP (/otp/send): minimum gap between two codes to the same address,
# so the endpoint can't be used to flood an inbox the caller doesn't own.
OTP_SEND_COOLDOWN_SECONDS = int(os.getenv("OTP_SEND_COOLDOWN_SECONDS", "60"))

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
# Left unset, it is derived below from FRONTEND_BASE_URL (+ "/verify"), which is
# where the main frontend's public /verify/:id page lives. Previously the
# fallback was always localhost, so a deploy that forgot this variable printed
# QR codes pointing at localhost:3001.
_FRONTEND_VERIFY_URL_ENV = os.getenv("FRONTEND_VERIFY_URL", "").strip().rstrip("/")

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

# Brevo HTTP API (https://api.brevo.com, port 443). Preferred over SMTP on hosts
# that block outbound SMTP ports (e.g. Render free tier). When set together
# with SMTP_FROM (a sender verified in Brevo), mailer.py uses it instead of SMTP.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()

# Base URL of the main frontend app, used to build deep links in owner
# status emails (e.g. {FRONTEND_BASE_URL}/app/owner/applications/<id>).
# Defaults to FRONTEND_LOGIN_URL minus its trailing "/login".
FRONTEND_BASE_URL = (
    os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/")
    or FRONTEND_LOGIN_URL.rstrip("/").removesuffix("/login")
)

FRONTEND_VERIFY_URL = _FRONTEND_VERIFY_URL_ENV or f"{FRONTEND_BASE_URL}/verify"

# Status-update emails to owners (app/services/owner_notifications.py).
# Master switch; they also require SMTP_* to be configured.
OWNER_EMAIL_NOTIFICATIONS_ENABLED = os.getenv("OWNER_EMAIL_NOTIFICATIONS_ENABLED", "true").lower() == "true"

# Days before certificate expiry at which a reminder email is sent.
EXPIRY_REMINDER_DAYS = tuple(
    sorted(
        {int(d) for d in os.getenv("EXPIRY_REMINDER_DAYS", "30,15,7,1").split(",") if d.strip().isdigit()},
        reverse=True,
    )
) or (30, 15, 7, 1)


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
    REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS = REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS
    PASSWORD_RESET_COOLDOWN_SECONDS = PASSWORD_RESET_COOLDOWN_SECONDS
    SELF_SERVICE_AUTH_ROLES = SELF_SERVICE_AUTH_ROLES
    MONGO_READ_PREFERENCE = MONGO_READ_PREFERENCE
    OTP_SEND_COOLDOWN_SECONDS = OTP_SEND_COOLDOWN_SECONDS
    AUDIT_LOG_RETENTION_DAYS = AUDIT_LOG_RETENTION_DAYS
    MFA_REQUIRED_ROLES = MFA_REQUIRED_ROLES
    MFA_TOKEN_EXPIRES_MINUTES = MFA_TOKEN_EXPIRES_MINUTES
    MFA_ISSUER = MFA_ISSUER
    MFA_RECOVERY_CODE_COUNT = MFA_RECOVERY_CODE_COUNT
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
    BREVO_API_KEY = BREVO_API_KEY
    FRONTEND_BASE_URL = FRONTEND_BASE_URL
    OWNER_EMAIL_NOTIFICATIONS_ENABLED = OWNER_EMAIL_NOTIFICATIONS_ENABLED
    EXPIRY_REMINDER_DAYS = EXPIRY_REMINDER_DAYS


settings = _Settings()
