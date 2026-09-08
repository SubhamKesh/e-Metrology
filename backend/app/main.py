from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pymongo.errors import PyMongoError

from app.config.db import init_indexes, client
from app.config.settings import MAX_REQUEST_BODY_BYTES
from app.routers import auth, instruments, applications, inspections, dashboard, certificates, uploads, ws, admin_users
from app.services.expiry_cron import start_expiry_scheduler
import os
from urllib.parse import urlparse

try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from app.rate_limit import limiter
    _SLOWAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - until `pip install -r requirements.txt` runs
    _SLOWAPI_AVAILABLE = False

app = FastAPI(title="MaapSetu API", version="1.0.0")

if _SLOWAPI_AVAILABLE:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # tighten this before final deployment
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """FastAPI/Starlette equivalent of helmet.js — there's no single
    canonical package for this in the Python ecosystem the way helmet
    dominates Express, so these are set directly. Kept intentionally small
    (no CSP tuned for a specific frontend build) to avoid breaking the
    Vite/React app's inline scripts/styles without dedicated testing."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # HSTS only makes sense once the app is actually served over HTTPS
    # (e.g. behind Render/Vercel's TLS termination) — harmless to send
    # locally over http, since browsers ignore HSTS on non-HTTPS origins.
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    """Rejects oversized request bodies before they're read into memory —
    mirrors the checklist's body-parser size limit. Relies on the
    client-supplied Content-Length header as a fast pre-check; it isn't a
    substitute for a body-size limit at the reverse proxy, which should
    also be set once this is deployed behind Nginx/a load balancer."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    # Attempt to initialise DB indexes and background jobs, but don't crash
    # the application if MongoDB isn't available (useful for local dev without
    # a running Mongo instance). Endpoints will still return 503 if DB is
    # required at request time.
    try:
        init_indexes()
        start_expiry_scheduler()
        # Explicitly ping the MongoDB client to confirm connectivity.
        try:
            client.admin.command("ping")
            app.state.db_ok = True
        except Exception:
            app.state.db_ok = False
    except Exception:
        # Keep the error short here; details are logged by the exception.
        app.state.db_ok = False


@app.exception_handler(PyMongoError)
async def pymongo_exception_handler(request: Request, exc: PyMongoError):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "db": bool(getattr(app.state, "db_ok", False))}


app.include_router(auth.router)
app.include_router(instruments.router)
app.include_router(applications.router)
app.include_router(inspections.router)
app.include_router(dashboard.router)
app.include_router(certificates.router)
app.include_router(uploads.router)
app.include_router(ws.router)
app.include_router(admin_users.router)


# Dev helper: expose whether MONGO_URI was loaded and the resolved host.
@app.get("/__dev/db-info")
def dev_db_info():
    uri = os.getenv("MONGO_URI", "")
    parsed = urlparse(uri) if uri else None
    host = parsed.hostname if parsed else None
    return {"mongo_uri_present": bool(uri), "mongo_host": host}