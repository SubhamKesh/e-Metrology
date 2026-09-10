<div align="center">

# ⚖️ MaapSetu — e‑Metrology

**Digital Legal Metrology Verification & Certification Platform for India**

Built for **Sih 2026 Hackathon**

[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](backend)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=white)](frontend)
[![Database](https://img.shields.io/badge/Database-MongoDB-47A248?logo=mongodb&logoColor=white)](#tech-stack)
[![License](https://img.shields.io/badge/License-Unspecified-lightgrey)](#license)

</div>

---

## 📖 Overview

**MaapSetu** ("Measurement Bridge") is a full‑stack digital platform that replaces the paper-based Legal Metrology verification and certification workflow used across India with an end‑to‑end online system.

Business owners register weighing/measuring instruments, submit them for verification, and get inspected by **Legal Metrology Officers (LMO)** and **GATC** authorities. Once approved, a **tamper‑evident, QR‑verifiable digital certificate** is issued — publicly verifiable by anyone (e.g. a consumer or auditor) without logging in, and automatically tracked through its validity/expiry lifecycle.

### Why it matters
- Removes manual paperwork and in-person queues for instrument certification.
- Gives every certificate a unique ID + QR code that resolves to a **public, tamper-proof verification page**.
- Automates certificate expiry tracking and renewal reminders.
- Provides role-based dashboards so owners, officers, and admins each see exactly what they need.

---

## ✨ Key Features

| Area | Capability |
|---|---|
| 🔐 **Authentication** | JWT access tokens + rotating, hashed refresh tokens in HttpOnly cookies; self-registration for business owners, invite-only provisioning for officers |
| 👥 **Role-based Access** | Four roles — `owner`, `lmo`, `gatc`, `admin` — each with a dedicated dashboard and permission scope |
| 🧰 **Instrument Registry** | Owners register weighing/measuring instruments with a unique serial number and auto-generated UIID |
| 📝 **Application Lifecycle** | State machine enforced server-side: `submitted → scheduled → inspected → certified/rejected → expiring → expired` |
| 🔎 **Inspection Workflow** | Officers scan a QR/UIID, review instrument details, and record inspection outcomes with photo evidence |
| 📜 **Digital Certificates** | Auto-generated PDF certificates (via ReportLab) with embedded QR codes linking to a public verification page |
| ✅ **Public Verification** | Anyone can verify a certificate's authenticity at `/verify/{cert_id}` — no login required |
| ⏰ **Expiry Automation** | Background scheduler (APScheduler) flags certificates approaching/at expiry and can notify owners |
| 📊 **Admin Dashboard** | System-wide analytics, user management, officer account provisioning with emailed temp passwords |
| 🔔 **Real-time Updates** | WebSocket channel for live application/queue status updates |
| 🛡️ **Hardened by Default** | Rate limiting, DDoS/request-flood protection, security headers, request-size caps, account lockout, and strict production startup guards |

---

## 🧱 Tech Stack

### Backend
| Component | Technology |
|---|---|
| Language / Framework | **Python 3.12** + **FastAPI** |
| Database | **MongoDB** (via `pymongo`) |
| Auth | **JWT** (`PyJWT`) + `passlib`/`bcrypt` password hashing |
| Validation | **Pydantic v2** |
| Rate limiting / DDoS | `slowapi`, custom middleware, optional **Redis**-backed shared state |
| File storage | **Cloudinary** (instrument/inspection photo uploads) |
| PDF generation | **ReportLab** |
| QR codes | `qrcode` |
| Scheduled jobs | **APScheduler** (certificate expiry checks) |
| Email | SMTP (officer onboarding, notifications) |
| Server | **Uvicorn** (ASGI) |
| Testing | `pytest` + `mongomock` |
| Linting | `ruff` |

### Frontend
| Component | Technology |
|---|---|
| Framework | **React 18** + **TypeScript** |
| Build tool | **Vite 5** |
| Routing | **React Router v6** |
| Data fetching / caching | **TanStack Query (React Query)** |
| Styling | **Tailwind CSS** |
| QR rendering | `qrcode.react` |
| Linting | ESLint (`typescript-eslint`) |

### Infrastructure & DevOps
| Component | Technology |
|---|---|
| Containerization | **Docker** (multi-stage, non-root backend image) |
| Local orchestration | **docker-compose** (MongoDB + optional Redis + backend) |
| CI/CD | **GitHub Actions** — lint → test → build for both backend and frontend, plus a Docker build check |
| Dependency updates | **Dependabot** |
| Target deployment | MongoDB Atlas + Render/Railway (backend), Vercel-style static host (frontend) |

---

## 🏗️ Architecture

```
┌──────────────────┐        HTTPS / REST + WebSocket        ┌──────────────────────┐
│   React + Vite    │  ───────────────────────────────────▶ │     FastAPI (ASGI)    │
│   Frontend (SPA)   │ ◀───────────────────────────────────  │   backend/app/main.py │
└──────────────────┘                                        └──────────┬────────────┘
                                                                          │
                    ┌────────────────────────┬────────────────┬─────────┴─────────┬──────────────┐
                    ▼                        ▼                ▼                   ▼              ▼
             MongoDB (Atlas /          Cloudinary       APScheduler          SMTP Server     Redis (opt.)
             local container)        (photo storage)   (expiry cron job)   (officer emails)  (shared DDoS
                                                                                               / rate-limit
                                                                                                 state)

┌────────────────────────────────────────────────────────────────────────────────────┐
│  Public, unauthenticated verification page (any client) → GET /certificates/verify  │
│  /{cert_id}  — powers the QR code printed on every issued certificate               │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Request flow (high level):**
1. `owner` registers an instrument → creates an `application`.
2. `admin`/system assigns the application to an `lmo`/`gatc` officer.
3. Officer inspects the instrument (scans UIID/QR, uploads evidence) → application moves through the enforced status state machine.
4. On approval, `cert_generator.py` produces a PDF certificate + QR code (`qr_generator.py`), uploaded via Cloudinary.
5. `expiry_cron.py` periodically transitions certificates to `expiring` → `expired`.
6. Anyone can scan the certificate's QR code to hit the public `/certificates/verify/{cert_id}` endpoint and confirm authenticity.

---

## 👤 User Roles

| Role | Access | Onboarding |
|---|---|---|
| **`owner`** | Registers instruments, submits applications, views own certificates | Public self-registration |
| **`lmo`** (Legal Metrology Officer) | Inspects assigned applications, records outcomes | Invite-only, created by admin |
| **`gatc`** | Same scope as LMO for its authority type | Invite-only, created by admin |
| **`admin`** (Super Admin / Minister) | Full system visibility, user management, officer provisioning | Seeded via `seed_super_admin.py` |

Officer accounts (`lmo` / `gatc`) are provisioned exclusively by an admin, who receives a one-time temporary password to relay (or which is emailed automatically); the officer must change it on first login.

---

## 📁 Project Structure

```
e-Metrology-main/
├── .github/
│   ├── workflows/ci.yml          # Lint → test → build pipeline (backend + frontend + docker)
│   └── dependabot.yml
├── docker-compose.yml            # Local dev: MongoDB (+ optional Redis) + backend container
├── docs/
│   ├── api-contract.md           # Full REST API reference / endpoint contract
│   ├── implementation_tasks.md   # Team task breakdown
│   └── security-hardening-status.md
│
├── backend/                      # FastAPI service
│   ├── app/
│   │   ├── main.py               # App factory, middleware, router registration, /health
│   │   ├── config/
│   │   │   ├── settings.py       # Env-driven config + production startup guards
│   │   │   ├── constants.py      # Roles, statuses, allowed state transitions
│   │   │   └── db.py             # Mongo client + index setup
│   │   ├── middleware/
│   │   │   ├── auth.py           # JWT auth dependency
│   │   │   ├── ddos_protection.py
│   │   │   └── ddos_store.py     # In-memory / Redis-backed request counters
│   │   ├── models/                # Pydantic schemas (user, instrument, application, inspection, dashboard)
│   │   ├── routers/               # REST endpoints
│   │   │   ├── auth.py
│   │   │   ├── instruments.py
│   │   │   ├── applications.py
│   │   │   ├── inspections.py
│   │   │   ├── certificates.py
│   │   │   ├── dashboard.py
│   │   │   ├── uploads.py
│   │   │   ├── admin_users.py
│   │   │   └── ws.py              # WebSocket live updates
│   │   ├── services/
│   │   │   ├── cert_generator.py  # PDF certificate generation
│   │   │   ├── qr_generator.py    # QR code generation
│   │   │   ├── uiid_generator.py  # Unique instrument ID generation
│   │   │   ├── status_transition.py # Enforces the application state machine
│   │   │   ├── expiry_cron.py     # APScheduler job for certificate expiry
│   │   │   ├── mailer.py          # SMTP email dispatch
│   │   │   └── notifications.py
│   │   ├── utils/
│   │   │   ├── security.py        # Password hashing, token helpers
│   │   │   └── upload_to_cloudinary.py
│   │   └── rate_limit.py
│   ├── seed/
│   │   ├── seed.py                # Seeds demo data
│   │   └── seed_data.py
│   ├── tests/                     # pytest suite (mongomock-backed, no live DB needed)
│   ├── seed_super_admin.py        # Creates/updates the Super Admin account
│   ├── Dockerfile                 # Multi-stage, non-root runtime image
│   ├── requirements.txt
│   ├── pyproject.toml             # ruff + pytest config
│   └── .env.example
│
└── frontend/                      # React + TypeScript SPA
    ├── src/
    │   ├── main.tsx / App.tsx     # Entry point + route definitions
    │   ├── pages/
    │   │   ├── auth/              # Login, Register, ChangePassword, PendingApproval
    │   │   ├── owner/             # Owner dashboard, instruments, applications, certificates
    │   │   ├── officer/           # Officer queue, inspection workflow, dashboard
    │   │   ├── admin/             # Admin dashboard, users, applications, certificates
    │   │   └── public/            # VerifyCertificate.tsx — public QR verification page
    │   ├── components/
    │   │   ├── ui/                 # Reusable primitives (Button, Card, DataTable, Field, StatusBadge...)
    │   │   ├── domain/             # Domain widgets (CertificateDetailCore, LifecycleTimeline, PhotoUploader...)
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
- **MongoDB** (local instance or [Docker](#option-b-docker-compose))
- *(Optional)* **Redis** — only needed to exercise the Redis-backed DDoS store locally
- *(Optional)* **Cloudinary** account — for photo uploads
- *(Optional)* **SMTP** credentials — for officer onboarding emails

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

# Seed a super admin account (reads SUPER_ADMIN_* from .env)
python seed_super_admin.py

# (Optional) seed demo data
python seed/seed.py

uvicorn app.main:app --reload --port 8000
```
Backend runs at **http://localhost:8000** — interactive API docs at **http://localhost:8000/docs**.

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
> The frontend is not included in `docker-compose.yml` — run it separately with `npm run dev` inside `frontend/`, pointed at the backend container's port.

---

## ⚙️ Environment Variables

### Backend (`backend/.env`)
| Variable | Description | Default |
|---|---|---|
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `DB_NAME` | Database name | `maapsetu` |
| `ENVIRONMENT` | `development` or `production` — production enables strict startup guards | `development` |
| `JWT_SECRET` | Signing secret for access tokens (32+ chars required in production) | — |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRES_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRES_DAYS` | Refresh token lifetime | `7` |
| `COOKIE_SECURE` | Must be `true` in production (HTTPS-only cookies) | `false` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:5173` |
| `REDIS_URL` | Optional — shared DDoS/rate-limit state across workers | *(unset → in-memory)* |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Photo upload storage | — |
| `FRONTEND_VERIFY_URL` | Public verification page base URL (embedded in certificate QR codes) | `http://localhost:3001/verify` |
| `FRONTEND_LOGIN_URL` | Login page URL used in officer onboarding emails | `http://localhost:5173/login` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_TLS` | Outgoing mail for officer credentials | *(optional — no-ops if unset)* |
| `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` / `SUPER_ADMIN_NAME` | Used once by `seed_super_admin.py` | — |

### Frontend (`frontend/.env`)
| Variable | Description | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Backend API root (no trailing slash, no `/api/v1`) | `http://localhost:8000` |

> ⚠️ In production, the backend **refuses to start** with a default/weak `JWT_SECRET`, `COOKIE_SECURE=false`, or an unset/localhost `CORS_ALLOWED_ORIGINS` — this is enforced fail-fast in `app/config/settings.py`.

---

## 📡 API Reference

Full endpoint contract lives in [`docs/api-contract.md`](docs/api-contract.md). Once the backend is running, interactive Swagger docs are available at:

```
http://localhost:8000/docs
```

Base path: `/api/v1` · Auth: `Authorization: Bearer <token>` (except endpoints marked **public**).

| Resource | Examples |
|---|---|
| **Auth** | `POST /auth/register` · `POST /auth/login` · `GET /auth/me` |
| **Instruments** | `POST /instruments` · `GET /instruments` · `GET /instruments/{id}` · `GET /instruments/by-uiid/{uiid}` |
| **Applications** | `POST /applications` · state-machine-driven status updates |
| **Inspections** | Officer inspection recording endpoints |
| **Certificates** | `GET /certificates/` · `GET /certificates/verify/{cert_id}` **(public)** |
| **Admin** | Officer account provisioning, user management |
| **Dashboard** | Role-scoped aggregated stats |
| **WebSocket** | Live queue/application status updates |
| **Health** | `GET /health` |

---

## 🔄 Application Lifecycle (State Machine)

```
submitted → scheduled → inspected → ┬→ certified → expiring → expired
                                      └→ rejected
```
Transitions are enforced centrally in `backend/app/services/status_transition.py` — no code path can skip a step or set an illegal status directly.

---

## 🛡️ Security

- Password hashing via `bcrypt`/`passlib`; JWT access tokens + rotating, hashed, HttpOnly refresh tokens.
- Account lockout with exponential backoff after repeated failed logins.
- DDoS/request-flood protection middleware (in-memory or Redis-backed across workers).
- Security response headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `HSTS`).
- Request body size limits.
- Strict production startup guards for secrets, cookie flags, and CORS.
- Debug routes (e.g. `/__dev/db-info`) are compiled out entirely outside development.

See [`docs/security-hardening-status.md`](docs/security-hardening-status.md) for the full hardening checklist and status.

---

## 🧪 Testing & CI

```bash
# Backend
cd backend
pip install -r requirements.txt ruff pytest mongomock
ruff check app/
pytest tests/ -v

# Frontend
cd frontend
npm run lint
npm run build     # type-checks and builds
```

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR to `main`:
1. **Backend** — lint (`ruff`) → test (`pytest` against `mongomock`, no live DB required)
2. **Frontend** — lint (`eslint`) → type-check + build (`tsc` + `vite build`)
3. **Docker** — verifies the backend image builds successfully

---

## 🗺️ Roadmap / Notes

- A deploy job is intentionally not yet wired into CI — pending target environment secrets (Render/Railway/Vercel).
- Certificate listing is currently unscoped server-side by role for some paths; see `docs/api-contract.md` for current vs. expected behavior.
- See [`docs/implementation_tasks.md`](docs/implementation_tasks.md) for the full team task breakdown.

---

## 👥 Team

Built by Team Tech Realist for **Sit 2026 Hackathon**.
Members:
1. Anushka Saha
2. Souradeep Tarafder
3. Subham Kesh
4. Kiran Kundu
5. Subhasis Pal
6. Aritra Sutradhar

---

## 📄 License

No license file is currently included in this repository — add one (e.g. MIT) before public distribution.
