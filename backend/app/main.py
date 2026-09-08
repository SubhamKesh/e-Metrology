from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pymongo.errors import PyMongoError

from app.config.db import init_indexes, client
from app.routers import auth, instruments, applications, inspections, dashboard, certificates, uploads, ws, admin_users
from app.services.expiry_cron import start_expiry_scheduler
import os
from urllib.parse import urlparse

app = FastAPI(title="MaapSetu API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # tighten this before final deployment
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


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