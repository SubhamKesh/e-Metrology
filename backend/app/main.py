from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.db import init_indexes
from app.routers import auth

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


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)

# Additional routers get included here as they're built:
# app.include_router(instruments.router)
# app.include_router(applications.router)
# app.include_router(inspections.router)
# app.include_router(certificates.router)
# app.include_router(dashboard.router)
