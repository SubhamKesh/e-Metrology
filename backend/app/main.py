from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.db import init_indexes
from app.routers import auth, instruments, applications, inspections, dashboard
from app.routers import certificates, verify
from app.services.expiry_corn import start_expiry_scheduler

app = FastAPI(title="MaapSetu API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before final deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_indexes()
    start_expiry_scheduler()


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(instruments.router)
app.include_router(applications.router)
app.include_router(inspections.router)
app.include_router(dashboard.router)
app.include_router(certificates.router)
app.include_router(verify.router)