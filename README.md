<div align="center">

# ⚖️ MaapSetu — e‑Metrology

**Digital Legal Metrology Verification & Certification Platform for India**

Built for **SIH 2026 Hackathon**

[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](backend)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=white)](frontend)
[![Database](https://img.shields.io/badge/Database-MongoDB-47A248?logo=mongodb&logoColor=white)](#-tech-stack)
[![Cache / Queue](https://img.shields.io/badge/Cache%20%2F%20Queue-Redis%20%2B%20RQ-DC382D?logo=redis&logoColor=white)](#-scaling--background-work)
[![License](https://img.shields.io/badge/License-Unspecified-lightgrey)](#-license)

</div>

---

## 📖 Overview

**MaapSetu** ("Measurement Bridge") is a full‑stack digital platform that replaces the paper-based Legal Metrology verification and certification workflow used across India with an end‑to‑end online system.

Business owners register weighing/measuring instruments, submit them for verification, and get inspected by **Legal Metrology Officers (LMO)** and **GATC** authorities. Once approved, a **tamper‑evident, QR‑verifiable digital certificate** is issued — publicly verifiable by anyone (e.g. a consumer or auditor) without logging in, and automatically tracked through its validity/expiry lifecycle.

### Why it matters
- Removes manual paperwork and in-person queues for instrument certification.
- Gives every certificate a unique ID + QR code that resolves to a **public verification page**.
- Automates certificate expiry tracking and renewal reminders.
- Provides role-based, jurisdiction-scoped dashboards so owners, officers, and admins each see exactly what they need.

---

## ✨ Key Features

| Area | Capability |
|---|---|
| 🔐 **Authentication** | JWT access tokens (15 min) + rotating, hashed refresh tokens in HttpOnly cookies; instant revocation via `token_version` (`/auth/logout-all`); self-registration for business owners, invite-only provisioning for officers |
| ✉️ **Email OTP Verification** | 6-digit, single-use, attempt-capped codes (HMAC-hashed, 10-minute expiry) via `/otp/send` + `/otp/verify`; verification proof is checked at registration |
| 👥 **Role-based Access** | Four roles — `owner`, `lmo`, `gatc`, `admin` — each with a dedicated dashboard and permission scope |
| 🗺️ **Jurisdiction Scoping** | States/UTs and districts stored as reference data; officers see only applications in their state/district, validated at write time |
| 🧰 **Instrument Registry** | Owners register instruments from a controlled list of instrument types, with a unique serial number and auto-generated UIID |
| 📝 **Application Lifecycle** | State machine enforced server-side: `submitted → scheduled → inspected → certified/rejected → expiring → expired` |
| 🔎 **Inspection Workflow** | Officers claim applications, scan a QR/UIID, review instrument details, and record outcomes with photo evidence |
| 📜 **Digital Certificates** | PDF certificates (ReportLab) with embedded QR codes linking to a public verification page; generated off the request path when Redis is available |
| ✅ **Public Verification** | Anyone can verify a certificate at `GET /api/v1/certificates/verify/{cert_id}` (frontend route `/verify/:certId`) — no login required; responses are cached |
| ⏰ **Expiry Automation** | Hourly APScheduler jobs move certificates to `expiring` / `expired`, guarded by a Redis run-lock so only one instance runs each tick |
| 📊 **Admin Dashboard** | System-wide analytics (cached for 60 s), user approval queue, officer account provisioning with emailed temp passwords |
| 🔔 **Real-time Updates** | Audience-scoped WebSocket notifications (`/ws/notifications`), fanned out across instances via Redis pub/sub; includes a `certificate_ready` event |
| 🛡️ **Hardened by Default** | Rate limiting, DDoS/request-flood protection, security headers, request-size caps, account lockout, DB-level `$jsonSchema` validation, and strict production startup guards |

---

## 🧱 Tech Stack

### Backend
| Component | Technology |
|---|---|
| Language / Framework | **Python 3.12** + **FastAPI** |
| Database | **MongoDB** (via `pymongo`, pooled: `maxPoolSize=50`) |
| Auth | **JWT** (`PyJWT`) + `passlib`/`bcrypt` password hashing |
| Validation | **Pydantic v2** (+ `email-validator`) plus MongoDB `$jsonSchema` |
| Rate limiting / DDoS | `slowapi`, custom middleware, **Redis**-backed shared state |
| Cache | Redis read-through cache (public cert verify, admin dashboard) |
| Background jobs | **RQ** (Redis Queue) worker — certificate generation and officer emails |
| Real-time | FastAPI WebSockets + Redis pub/sub for cross-instance delivery |
| File storage | **Cloudinary** (instrument/inspection photos and certificate PDFs) |
| PDF generation | **ReportLab** |
| QR codes | `qrcode` (Pillow) |
| Scheduled jobs | **APScheduler** (hourly certificate expiry checks) |
| Email | SMTP via stdlib `smtplib` (officer onboarding, OTP codes) |
| Server | **Uvicorn** (ASGI) |
| Testing | `pytest` + `mongomock` + `httpx` |
| Linting | `ruff` |

> Redis is **optional**: every Redis-backed feature falls back to per-process/inline behaviour when `REDIS_URL` is unset, so local development needs only MongoDB.

### Frontend
| Component | Technology |
|---|---|
| Framework | **React 18** + **TypeScript** |
| Build tool | **Vite 5** |
| Routing | **React Router v6** |
| Data fetching / caching | **TanStack Query (React Query) v5** |
| Styling | **Tailwind CSS 3** |
| QR rendering | `qrcode.react` |
| Linting | ESLint 9 (`typescript-eslint`) |

### Infrastructure & DevOps
| Component | Technology |
|---|---|
| Containerization | **Docker** (multi-stage, non-root backend image, `/api/v1/health` healthcheck, 2 uvicorn workers) |
| Local orchestration | **docker-compose** (MongoDB + optional Redis + backend) |
| CI/CD | **GitHub Actions** — lint → test → build for both backend and frontend, plus a Docker build check |
| Dependency updates | **Dependabot** |
| Target deployment | MongoDB Atlas + Render/Railway (backend), Vercel-style static host (frontend) |

---

## 🏗️ Architecture

```
┌──────────────────┐     HTTPS / REST + WebSocket      ┌───────────────────────┐
│   React + Vite    │ ────────────────────────────────▶ │     FastAPI (ASGI)     │
│   Frontend (SPA)   │ ◀──────────────────────────────── │   backend/app/main.py  │
└──────────────────┘                                   └───────────┬───────────┘
                                                                     │
      ┌───────────────┬──────────────────┬──────────────┬───────────┴────────┐
      ▼               ▼                  ▼              ▼                    ▼
 MongoDB          Cloudinary        APScheduler     SMTP server        Redis (optional)
 (Atlas /         (photos +         (hourly expiry  (officer emails,   ├─ DDoS / rate-limit state
  local)           cert PDFs)         jobs)           OTP codes)        ├─ WebSocket pub/sub fan-out
                                                                        ├─ Scheduler run-lock
                                                                        ├─ Read-through cache
                                                                        └─ RQ job queue
                                                                               │
                                                                               ▼
                                                                    RQ worker (run_worker.py)
                                                                    ├─ generate_certificate_job
                                                                    └─ send_officer_credentials_job

┌───────────────────────────────────────────────────────────────────────────────┐
│ Public, unauthenticated verification: GET /api/v1/certificates/verify/{cert_id} │
│ — powers the QR code printed on every issued certificate                        │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Request flow (high level):**
1. `owner` registers an instrument → creates an `application` (scoped to a state/district).
2. An `lmo`/`gatc` officer in that jurisdiction claims the application (`/applications/{id}/claim`).
3. The officer submits an inspection (evidence photos uploaded via Cloudinary) → the application moves through the enforced status state machine.
4. On a passing inspection, certificate generation (`cert_generator.py` → PDF + `qr_generator.py` → QR code, both uploaded to Cloudinary) is **enqueued to the RQ worker** if `REDIS_URL` is set, otherwise it runs inline.
5. When the certificate is ready, a `certificate_ready` WebSocket event is pushed to the owner and the assigned officer.
6. `expiry_cron.py` runs hourly and transitions certificates to `expiring` → `expired`.
7. Anyone can scan the certificate's QR code to hit the public verify endpoint and confirm authenticity.

---

## ⚡ Scaling & Background Work

Set `REDIS_URL` to switch these on. Without it, the app runs as a single-process service with the fallback shown.

| Concern | With `REDIS_URL` | Without |
|---|---|---|
| DDoS / request-flood counters | Shared Redis sorted-set sliding window (`ddos_store.py`) | Per-worker in-memory counters (threshold effectively multiplied by worker count) |
| WebSocket notifications | Published to a Redis channel; every instance forwards to its own local clients (`ws_pubsub.py`) | Delivered to clients on the same instance only |
| Expiry scheduler | `SET NX` run-lock — one instance per tick | Every instance runs the job |
| Public verify + admin dashboard | Read-through cache (300 s / 60 s TTL) | Always queries MongoDB |
| Certificate generation | Enqueued to RQ worker; owner notified via `certificate_ready` | Runs inline in the inspection request |
| Officer credential emails | Enqueued to RQ worker (`emailed` in the response means "queued") | Sent inline during officer creation |

**Running the worker** (separate long-lived process, same venv as uvicorn):
```bash
cd backend
python run_worker.py
```
The worker uses `rq.SimpleWorker` so it also runs on Windows (no `os.fork`). On Linux production hosts you can switch to `rq.Worker` for per-job timeouts. Failed jobs stay visible in RQ's `FailedJobRegistry` rather than being lost.

---

## 👤 User Roles

| Role | Access | Onboarding |
|---|---|---|
| **`owner`** | Registers instruments, submits applications, views own certificates | Public self-registration (email OTP verified) |
| **`lmo`** (Legal Metrology Officer) | Inspects applications in their jurisdiction, records outcomes | Invite-only, created by admin; requires admin approval |
| **`gatc`** | Same scope as LMO for its authority type | Invite-only, created by admin; requires admin approval |
| **`admin`** (Super Admin / Minister) | Full system visibility, user management, officer provisioning and approval | Seeded via `seed_super_admin.py` |

Officer accounts (`lmo` / `gatc`) are provisioned exclusively by an admin, who receives a one-time temporary password to relay (it's also emailed automatically when SMTP is configured); the officer must change it on first login.

---

## 📁 Project Structure

```
e-Metrology-main/
├── .github/
│   ├── workflows/ci.yml            # Lint → test → build pipeline (backend + frontend + docker)
│   └── dependabot.yml
├── docker-compose.yml              # Local dev: MongoDB (+ optional Redis) + backend container
├── docs/
│   ├── api-contract.md             # Full REST API reference / endpoint contract
│   ├── implementation_tasks.md     # Team task breakdown
│   └── security-hardening-status.md
│
├── backend/                        # FastAPI service
│   ├── app/
│   │   ├── main.py                 # App setup, middleware, router registration, startup/shutdown, /health
│   │   ├── rate_limit.py           # slowapi limiter (5 attempts / 15 min on auth routes)
│   │   ├── config/
│   │   │   ├── settings.py         # Env-driven config + production startup guards
│   │   │   ├── constants.py        # Roles, statuses, allowed state transitions
│   │   │   ├── db.py               # Mongo client, collections, indexes, $jsonSchema validation
│   │   │   ├── geo_data.py         # 36 states/UTs reference list
│   │   │   └── instrument_specs.py # Allowed instrument types and their specs
│   │   ├── middleware/
│   │   │   ├── auth.py             # JWT auth dependency + role_required()
│   │   │   ├── ddos_protection.py
│   │   │   └── ddos_store.py       # In-memory / Redis-backed request counters
│   │   ├── models/                 # Pydantic schemas (user, instrument, application, inspection, dashboard, geo, otp)
│   │   ├── routers/                # REST + WebSocket endpoints
│   │   │   ├── auth.py             # register, login, refresh, logout, logout-all, me, change-password
│   │   │   ├── otp.py              # Email OTP send / verify
│   │   │   ├── geo.py              # States and districts lookups
│   │   │   ├── instruments.py
│   │   │   ├── applications.py
│   │   │   ├── inspections.py
│   │   │   ├── certificates.py
│   │   │   ├── dashboard.py
│   │   │   ├── uploads.py
│   │   │   ├── admin_users.py      # Officer creation, approval queue
│   │   │   └── ws.py               # /ws/notifications
│   │   ├── services/
│   │   │   ├── cert_generator.py   # PDF certificate generation
│   │   │   ├── qr_generator.py     # QR code generation
│   │   │   ├── uiid_generator.py   # Unique instrument ID generation
│   │   │   ├── status_transition.py# Enforces the application state machine
│   │   │   ├── expiry_cron.py      # APScheduler jobs + Redis run-lock
│   │   │   ├── jobs.py             # RQ queue + job definitions (certificate, email)
│   │   │   ├── notifications.py    # Audience-scoped WebSocket delivery
│   │   │   ├── ws_pubsub.py        # Redis pub/sub subscriber for cross-instance fan-out
│   │   │   ├── otp.py              # OTP generation, hashing, verification
│   │   │   └── mailer.py           # SMTP email dispatch
│   │   └── utils/
│   │       ├── security.py         # Password hashing, token helpers
│   │       ├── cache.py            # Redis read-through cache (no-op without Redis)
│   │       ├── validators.py       # Input validation helpers
│   │       ├── geo_validation.py   # State/district checks against reference data
│   │       ├── location_format.py
│   │       └── upload_to_cloudinary.py
│   ├── seed/
│   │   ├── seed.py                 # Seeds demo data (wipes its collections first)
│   │   ├── seed_data.py
│   │   └── districts.csv           # District reference data (code, name, state_code)
│   ├── tests/                      # pytest suite (mongomock-backed, no live DB needed)
│   ├── run_worker.py               # RQ worker process
│   ├── seed_super_admin.py         # Creates/updates the Super Admin account
│   ├── seed_geo.py                 # Upserts states/UTs and districts
│   ├── fix_certificate_pdf_urls.py # One-off migration for old certificate PDF URLs
│   ├── burst_test.py               # Quick request-burst check for DDoS protection
│   ├── ws_listener.py              # CLI WebSocket listener for testing notifications
│   ├── Dockerfile                  # Multi-stage, non-root runtime image
│   ├── requirements.txt
│   ├── pyproject.toml              # ruff + pytest config
│   └── .env.example
│
└── frontend/                       # React + TypeScript SPA
    ├── src/
    │   ├── main.tsx / App.tsx      # Entry point + route definitions
    │   ├── pages/
    │   │   ├── auth/               # Login, Register, ChangePassword, PendingApproval
    │   │   ├── owner/              # Dashboard, instruments, applications, certificates
    │   │   ├── officer/            # Queue, inspection workflow, dashboard, certificates
    │   │   ├── admin/              # Dashboard, users, instruments, applications, certificates
    │   │   └── public/             # VerifyCertificate.tsx — public QR verification page
    │   ├── components/
    │   │   ├── ui/                 # Reusable primitives (Button, Card, DataTable, Field, StatusBadge...)
    │   │   ├── domain/             # CertificateDetailCore, LifecycleTimeline, PhotoUploader...
    │   │   └── layout/AppShell.tsx
    │   ├── context/AuthContext.tsx
    │   ├── routes/ProtectedRoute.tsx
    │   ├── hooks/useData.ts        # React Query hooks
    │   └── lib/                    # api.ts, endpoints.ts, types.ts, validation.ts, nav.ts, roleHome.ts
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.ts
    └── .env.example
```

---

## 🚀 Getting Started

### Prerequisites
- **Python** 3.12+
- **Node.js** 20+ and npm
- **MongoDB** (local instance or [Docker](#option-b--docker-compose))
- *(Optional)* **Redis** — enables shared DDoS state, WebSocket fan-out, caching, the scheduler lock, and the background job queue
- *(Optional)* **Cloudinary** account — for photo uploads and certificate PDFs
- *(Optional)* **SMTP** credentials — for OTP codes and officer onboarding emails

### Option A — Manual Setup

**1. Clone the repository**
```bash
git clone <repository-url>
cd e-Metrology-main
```

**2. Backend setup**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # fill in Mongo URI, JWT secret, Cloudinary, SMTP, etc.

# Seed states/UTs (and districts, if seed/districts.csv is present)
python seed_geo.py

# Seed a super admin account (reads SUPER_ADMIN_* from .env)
python seed_super_admin.py

# (Optional) seed demo data — wipes and reloads the demo collections
python -m seed.seed

uvicorn app.main:app --reload --port 8000
```
Backend runs at **http://localhost:8000** — interactive API docs at **http://localhost:8000/docs**.

**Optional — background worker** (only if `REDIS_URL` is set), in a second terminal with the same venv:
```bash
cd backend
python run_worker.py
```

**3. Frontend setup**
```bash
cd frontend
npm install
cp .env.example .env             # set VITE_API_BASE_URL=http://localhost:8000
npm run dev
```
Frontend runs at **http://localhost:5173**.

### Option B — Docker Compose

```bash
docker compose up --build
```
This starts MongoDB and the backend container (`http://localhost:8000`). Add `--profile redis` to also start Redis:
```bash
docker compose --profile redis up --build
```
> Notes:
> - To use Redis from the backend container, uncomment `REDIS_URL: redis://redis:6379/0` in `docker-compose.yml`.
> - `docker-compose.yml` does not include the RQ worker or the frontend. Run the worker with `python run_worker.py` (same `REDIS_URL`, reachable MongoDB) and the frontend with `npm run dev` inside `frontend/`.
> - The compose file is for local development only; it is not the production deployment shape.

---

## ⚙️ Environment Variables

### Backend (`backend/.env`)
| Variable | Description | Default |
|---|---|---|
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `DB_NAME` | Database name | `maapsetu` |
| `ENVIRONMENT` | `development` or `production` — production enables strict startup guards | `development` |
| `JWT_SECRET` | Signing secret for access tokens (32+ chars required in production) | `dev_secret_change_me` (dev only) |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRES_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRES_DAYS` | Refresh token lifetime | `7` |
| `REFRESH_COOKIE_NAME` | Name of the refresh-token cookie | `refresh_token` |
| `COOKIE_SECURE` | Must be `true` in production (HTTPS-only cookies) | `false` |
| `COOKIE_SAMESITE` | SameSite policy for the refresh cookie | `strict` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:5173` |
| `LOGIN_MAX_ATTEMPTS` | Failed logins before lockout begins | `5` |
| `LOGIN_LOCKOUT_BASE_MINUTES` | Base lockout duration (doubles on each repeat) | `1` |
| `MAX_REQUEST_BODY_BYTES` | Maximum request body size | `2097152` (2 MB) |
| `REDIS_URL` | Optional — enables shared DDoS state, WS fan-out, cache, scheduler lock, and the job queue | *(unset → in-process fallbacks)* |
| `OTP_PEPPER` | Secret used to HMAC-hash OTP codes. **Set this outside local dev** — a warning is logged and an insecure default is used if unset | *(insecure dev default)* |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Photo and certificate PDF storage | — |
| `FRONTEND_VERIFY_URL` | Public verification page base URL (embedded in certificate QR codes) | `http://localhost:3001/verify` |
| `FRONTEND_LOGIN_URL` | Login page URL used in officer onboarding emails | `http://localhost:5173/login` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_TLS` | Outgoing mail (OTP codes, officer credentials) | *(optional — no-ops if `SMTP_HOST`/`SMTP_FROM` unset)* |
| `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` / `SUPER_ADMIN_NAME` | Used once by `seed_super_admin.py` | — |

### Frontend (`frontend/.env`)
| Variable | Description | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Backend API root (no trailing slash, no `/api/v1`) | `http://localhost:8000` |

> ⚠️ In production, the backend **refuses to start** with a default/weak `JWT_SECRET`, `COOKIE_SECURE=false`, or an unset/localhost `CORS_ALLOWED_ORIGINS` — this is enforced fail-fast in `app/config/settings.py`. With `ENVIRONMENT=production` and no `REDIS_URL`, it starts but logs a warning about per-worker DDoS/WebSocket state.

---

## 📡 API Reference

Full endpoint contract lives in [`docs/api-contract.md`](docs/api-contract.md). Once the backend is running, interactive Swagger docs are available at:

```
http://localhost:8000/docs
```

Base path: `/api/v1` · Auth: `Authorization: Bearer <token>` (except endpoints marked **public**).

| Resource | Examples |
|---|---|
| **Auth** | `POST /auth/register` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `POST /auth/logout-all` · `GET /auth/me` · `POST /auth/change-password` |
| **OTP** | `POST /otp/send` · `POST /otp/verify` **(public)** |
| **Geo** | `GET /geo/states` · `GET /geo/states/{state_code}/districts` |
| **Instruments** | `POST /instruments` · `GET /instruments` · `GET /instruments/{id}` · `GET /instruments/by-uiid/{uiid}` · `GET /instruments/meta/types` |
| **Applications** | `POST /applications` · `GET /applications` · `GET /applications/{id}` · `POST /applications/{id}/claim` |
| **Inspections** | `POST /inspections` · `GET /inspections/{id}` |
| **Certificates** | `GET /certificates/` · `GET /certificates/{cert_id}` · `GET /certificates/verify/{cert_id}` **(public)** |
| **Uploads** | `POST /uploads/photo` |
| **Admin** | `POST /admin/users/create-officer` · `GET /admin/users` · `GET /admin/users/pending` · `POST /admin/users/{id}/approve` · `POST /admin/users/{id}/reject` |
| **Dashboard** | `GET /dashboard/owner` · `/lmo` · `/gatc` · `/admin` |
| **WebSocket** | `/ws/notifications?token=<access token>` — live application, queue, and certificate updates |
| **Health** | `GET /api/v1/health` |

---

## 🔄 Application Lifecycle (State Machine)

```
submitted → scheduled → inspected → ┬→ certified → expiring → expired
                                      └→ rejected
```
Transitions are enforced centrally in `backend/app/services/status_transition.py` — no code path can skip a step or set an illegal status directly.

---

## 🛡️ Security

- Password hashing via `bcrypt`/`passlib`; JWT access tokens (15 min) + rotating, hashed, HttpOnly refresh tokens with reuse detection.
- Instant token revocation via a per-user `token_version` (`/auth/logout-all`).
- Account lockout with exponential backoff after repeated failed logins; `slowapi` rate limit on `/login` and `/register`.
- Email OTPs are HMAC-hashed with a server-side pepper, single-use, expire after 10 minutes, and are capped at 5 attempts.
- DDoS/request-flood protection middleware (in-memory or Redis-backed across workers).
- Security response headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `HSTS`).
- Request body size limits; MongoDB `$jsonSchema` validation as a second gate behind Pydantic.
- WebSocket connections are authenticated, restricted to `active` accounts, and every message is delivered only to its intended audience (fails closed).
- Strict production startup guards for secrets, cookie flags, and CORS.
- Debug routes (e.g. `/__dev/db-info`) are not mounted outside development.

See [`docs/security-hardening-status.md`](docs/security-hardening-status.md) for the full hardening checklist and status.

---

## 🧪 Testing & CI

```bash
# Backend
cd backend
pip install -r requirements.txt     # includes pytest, mongomock, httpx, ruff
ruff check app/
pytest tests/ -v

# Frontend
cd frontend
npm run lint
npm run build     # type-checks and builds
```

The backend suite covers auth hardening (lockout, refresh rotation, logout-all, headers, body limits), production startup guards, application-ID matching, and WebSocket notification scoping. It runs against `mongomock`, so no live database is required.

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR to `main`:
1. **Backend** — lint (`ruff`) → test (`pytest` against `mongomock`, no live DB required)
2. **Frontend** — lint (`eslint`) → type-check + build (`tsc` + `vite build`)
3. **Docker** — verifies the backend image builds successfully

Handy manual checks: `python burst_test.py` fires a burst of requests to exercise DDoS protection, and `python ws_listener.py <port> <access_token>` prints live WebSocket notifications (run it against two instances to check cross-instance fan-out).

---

## 🗺️ Roadmap / Notes

- **Scaling — done:** Redis-backed DDoS state, WebSocket fan-out, scheduler run-lock, read-through caching, audience-scoped notifications, and certificate generation + officer emails moved to a background worker.
- **Scaling — still to do:** MongoDB read replicas (`secondaryPreferred` for read-heavy paths), and deployment-level work — load balancer with multiple backend instances, autoscaling, and a CDN.
- The RQ worker is not yet part of `docker-compose.yml`, and a deploy job is intentionally not wired into CI — pending target environment secrets (Render/Railway/Vercel).
- Certificate listing (`GET /certificates/`) is currently unscoped by role server-side; see `docs/api-contract.md` for current vs. expected behavior.
- `POST /otp/send` does not yet have its own rate limit, so it should be limited before it is exposed publicly.
- See [`docs/implementation_tasks.md`](docs/implementation_tasks.md) for the team task breakdown.

---

## 👥 Team

Built by Team Tech Realist for **SIH 2026 Hackathon**.
Members:
1. Anushka Saha
2. Souradeep Tarafdar
3. Subham Kesh
4. Kiran Kundu
5. Subhasis Pal
6. Aritra Sutradhar

---

## 📄 License

No license file is currently included in this repository.