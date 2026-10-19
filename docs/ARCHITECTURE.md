# MaapSetu — Architecture, Security & Deployment

One document that explains how the system is built, how it is protected, and how to run it. It
summarises and links to the detailed documents rather than replacing them:

| For the detail on… | Read |
|---|---|
| Every endpoint, request and response | [`api-contract.md`](api-contract.md) |
| Scaling, load balancer, autoscaling, CDN, read replicas | [`deployment-scaling.md`](deployment-scaling.md) |
| The security checklist, item by item | [`security-hardening-status.md`](security-hardening-status.md) |
| What was built, when, and what is still open | [`CHANGELOG-requirements.md`](CHANGELOG-requirements.md) |
| Environment variables, local setup, testing | the root [`README.md`](../README.md) |

**How to read the claims in this document.** Everything stated as fact was checked against the code
in this repository. Where something is only possible in a hosting provider's dashboard, or has not been
run against a real provider or device, it is labelled **(infra)** or **(not verified)**. Section 10 lists
what is deliberately not covered.

---

## 1. What the system is

MaapSetu replaces the paper Legal Metrology verification process. A business owner registers a
weighing or measuring instrument and applies for verification; a Legal Metrology Officer inspects it
in the field; on a pass the system issues a PDF certificate with a QR code that anyone can check on a
public page, then tracks it to expiry and renewal.

| Role | What they do | How they get an account |
|---|---|---|
| `owner` | Register instruments, upload required documents, apply, track, renew | Self-registration with an emailed code |
| `lmo`, `gatc` | Claim and inspect applications in their state/district; oversight pages | Created by an admin, who approves them |
| `admin` | Everything, nationally: users, validity periods, audit log, oversight, reports | Seeded by the operator (`seed_super_admin.py`) |
| *anyone* | Verify a certificate by QR or number, no login | — |

---

## 2. System architecture

```
 Browser / installed PWA (React + Vite, static files on a CDN)
        │  HTTPS  REST  /api/v1/*        WebSocket  /ws/notifications
        ▼
 [ optional load balancer / WAF ]   ← overwrites X-Forwarded-For, passes WebSockets  (infra)
        ▼
 FastAPI app  (uvicorn, 2 workers per container; any number of containers)
   middleware order, outermost first:
     DDoS sliding window → CORS → request-size limit → security headers → router
   routers: auth · otp · instruments · instrument_documents · applications · inspections ·
            certificates · dashboard · oversight · enforcement_cases · reports ·
            admin_users · admin_audit · admin_validity · geo · uploads · ws
   services: status_transition · scheduling · inspection_form · cert_generator · qr_generator ·
             owner_notifications · mailer · expiry_cron · audit · otp · validity · report_export …
        │
        ├── MongoDB (Atlas)        system of record; 16 collections (see §4)
        ├── Cloudinary             photos, supporting documents, avatars, certificate PDFs
        ├── Brevo API or SMTP      OTP codes, officer credentials, owner status emails
        └── Redis (optional)       shared limits & counters · cache · WebSocket pub/sub ·
                                   scheduler lock · RQ job queue
                                         │
                                         ▼
                            RQ worker — embedded in each web process by default, or a separate
                            `python run_worker.py` service (EMBEDDED_WORKER=false)
                            jobs: generate certificate · officer credential email · owner email
```

### Design decisions worth knowing

- **One backend, one database, one language.** A single FastAPI service keeps the hackathon-to-pilot
  path simple. There are no microservices to coordinate.
- **Redis is optional, not required.** Every Redis-backed feature has a defined fallback (per-process
  memory, inline work, local-only WebSockets), so local development needs only MongoDB. The price is
  that fallbacks are per-process: **with more than one worker or instance, set `REDIS_URL`** or limits
  and WebSocket delivery are not shared (a warning is logged in production).
- **Slow work leaves the request.** Certificate PDF generation and all emails go through a queue when
  Redis is present, so an inspection submission returns quickly. Without Redis they run inline or in a
  short-lived thread.
- **Server is the authority.** The frontend hides what a role cannot use, but every rule — state
  transitions, jurisdiction, the inspection form, the password policy, upload types — is enforced in the
  backend and covered by tests.
- **Reference data is data.** States/UTs and districts are collections (seeded by `seed_geo.py`), and
  every state/district code written anywhere is validated against them. Per-type certificate validity
  lives in `validity_rules`, editable by an admin without a deploy.

### The application lifecycle

```
submitted → scheduled → inspected → ┬→ certified → expiring → expired
                                    └→ rejected
```

`services/status_transition.py` is the only place a status can change, so no route can skip a step.
Typical flow: the owner submits → an officer in that jurisdiction claims it (or an admin assigns one)
and a date + slot is booked → the officer scans the instrument's QR, records readings, checks, seal
number, photos and a mandatory GPS fix → on a pass a certificate job is queued → the owner is told by
WebSocket and email → an hourly job moves certificates to `expiring`/`expired` and sends reminders at
30/15/7/1 days.

### Frontend

React 18 + TypeScript + Vite, React Router, TanStack Query, Tailwind. Public pages are prerendered at
build time; authenticated routes use a generic shell. It is an installable PWA: the service worker caches
**only static files** (app shell and built assets) — never API responses, certificates or personal data.
Officers' assigned work, drafts and finished-but-unsent inspections live in IndexedDB on the device and
sync automatically (idempotency key per inspection, so a retry cannot duplicate). See the README's
*Offline Inspections* section.

---

## 3. Request paths

**Sign-in (owner).** `POST /auth/login` → password checked (bcrypt) → lockout counter consulted →
15-minute access token (JWT, carries `token_version`) in the response body, and a random refresh token
in an HttpOnly cookie. `POST /auth/refresh` rotates the refresh token; presenting an already-rotated
one is rejected and audited.

**Sign-in (officer / admin).** After the password, the server returns only a short-lived (10 min)
`mfa_token`. No access token, cookie or user data is released until a valid authenticator code (or a
one-time recovery code) is submitted.

**Certificate verification (public).** `GET /certificates/verify/{id-or-number}` — no login. Looks up the
certificate, its instrument and the owner's organisation, and returns validity. Read through a Redis
cache (300 s) when available; `is_expired` is recomputed on every call, so a cache hit can never report an
expired certificate as current.

**Live updates.** `/ws/notifications?token=…` authenticates the access token, requires an `active`
account, and delivers each message only to its intended audience (fails closed). With Redis, events fan
out across instances through pub/sub.

---

## 4. Data model

MongoDB, accessed through `pymongo` (pool of up to 50 connections per process). Pydantic validates every
request; a MongoDB `$jsonSchema` validator on `users`, `instruments`, `applications`, `refresh_tokens` and
`otp_verifications` is a second, independent gate (applied with `collMod`, "moderate" level so old
documents don't break; if the DB user lacks the privilege, startup logs it and continues).

| Collection | Holds | Notable indexes / lifetime |
|---|---|---|
| `users` | Accounts, role, status, jurisdiction, `token_version`, lockout counters, encrypted 2-step secret | unique `email` |
| `instruments` | Registered instruments, UIID, location | unique `uiid`; (state, district) |
| `applications` | Verification applications and their status, schedule, assigned officer | status, (instrument, status), (officer, date, slot), (state, district, …) |
| `inspections` | Outcome, readings, checks, seal number, photos, GPS, how it was identified | partial-unique `client_id` (offline idempotency) and `seal_number` (a seal is used once) |
| `certificates` | Issued certificates, validity window, seal number, PDF URL | unique `cert_no`; unique `application_id` |
| `instrument_documents` | Owner's required documents (metadata + Cloudinary URL) | unique (instrument, slot) |
| `enforcement_cases` | Notices and escalation for lapsed / never-certified instruments | at most one active case per instrument |
| `validity_rules` | Admin-set validity days per instrument type | unique `type` |
| `refresh_tokens` | SHA-256 hash of each refresh token, revoked flag | unique hash; **TTL** at `expires_at` |
| `otp_verifications` | HMAC-hashed email/reset codes, attempts, expiry | unique (identifier, purpose); **TTL** |
| `audit_logs` | Append-only security trail | **TTL** `AUDIT_LOG_RETENTION_DAYS` (default 365, minimum 180) |
| `email_log` | One document per owner email; `_id` is the dedupe key | — |
| `alerts` | Expiry-alert records written by the hourly job (so each is raised once) | — |
| `counters` | Sequence counters used to generate UIIDs | — |
| `states`, `districts` | Reference data | unique codes |

**Jurisdiction.** An officer's state/district is stored on their account. List and detail queries for
applications, certificates, instruments, reports and oversight are filtered by it on the server; a
search filter can narrow but never widen what a role may see (tested).

---

## 5. Security

### 5.1 Layers

| Layer | Control | Where |
|---|---|---|
| Network edge **(infra)** | TLS termination, WAF / absorbing volumetric floods, Atlas IP allow-list | Host / Cloudflare / Atlas dashboards |
| Request flood | Per-IP sliding window (60 requests / 10 s) → 5-minute block; repeat offenders 1 hour. Shared across workers via Redis | `middleware/ddos_protection.py`, `ddos_store.py` |
| Transport headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `HSTS` | `main.py` |
| Request limits | Body cap (2 MB default, `Content-Length` pre-check); per-type upload caps | `main.py`, `utils/file_checks.py` |
| Identity | bcrypt passwords, policy, lockout, rotating tokens, mandatory 2-step for officers/admin | §5.2 |
| Authorisation | `role_required()` per route + server-side jurisdiction scoping | `middleware/auth.py` |
| Input | Pydantic + `$jsonSchema`; state/district codes checked against reference data; file type read from the file's first bytes, not the filename or Content-Type | models, `db.py`, `file_checks.py` |
| Output | HTML-escaped email templates; spreadsheet formulas defused in CSV exports | `email_templates.py`, `report_export.py` |
| Secrets & config | Production refuses to start with a weak `JWT_SECRET`, `COOKIE_SECURE=false`, or default/`*` CORS; debug routes not mounted | `config/settings.py` |
| Accountability | Audit trail, no edit/delete API | §5.4 |

### 5.2 Authentication and sessions

- **Passwords:** 8–64 chars with upper, lower, digit and special character; common passwords refused;
  checked when set (register, change, reset), not at login, so older accounts still sign in.
- **Tokens:** access token 15 min. Refresh token is random (not a JWT), stored only as a SHA-256 hash,
  HttpOnly cookie, rotated on every use; reuse of a rotated token is refused.
- **Instant revocation without Redis:** every access token carries the user's `token_version`, checked on
  each request. Logout-all, password change/reset and suspension bump it, so outstanding tokens die at
  once. Refresh also refuses accounts that are no longer `active`.
- **Lockout:** 5 failures, then 1, 2, 4, 8… minute backoff, per account. Failed two-step codes count
  against the same counter, and the counter is cleared only after the second step succeeds.
- **Two-step verification (officer, admin):** TOTP (RFC 6238, implemented on the standard library and
  tested against the RFC vectors). A used time-step cannot be replayed; 8 one-time recovery codes, stored
  only as keyed hashes; secrets encrypted at rest with Fernet (`MFA_ENCRYPTION_KEY`). Officer/admin refresh
  tokens must carry a "second step done" mark, so a session cannot be renewed from a password alone.
- **Recovery paths:** owners reset a forgotten password by emailed code (anti-enumeration, single use,
  5 attempts, 60 s cooldown). Officers: an admin resets the password or the 2-step. Admin: the operator
  runs `seed_super_admin.py` / `reset_mfa.py`.
- **"Remember me"** (30 days) is honoured for owners only, enforced server-side.
- **Codes:** email OTP and reset codes are HMAC-hashed with `OTP_PEPPER`, expire in 10 minutes, and the
  attempt cap is counted atomically so parallel guesses cannot exceed it.

### 5.3 Data protection

- **In transit:** HTTPS is terminated by the host (**infra**); the app sets HSTS and, in production,
  refuses to run with non-secure cookies.
- **At rest:** passwords bcrypt-hashed; refresh tokens and codes stored hashed; authenticator secrets
  encrypted. Database and Cloudinary encryption at rest are provider features **(infra, verify on your
  cluster/account)**.
- **Uploaded files:** type sniffed from content; size capped (2 MB avatar, 5 MB documents); stored in
  Cloudinary, with only the URL and metadata in MongoDB.
- **What the public can see:** the verify page shows certificate number, seal number, validity dates,
  instrument type/make/model/UIID and the owner's organisation name — and nothing from the inspection
  record, officer or GPS. Owners likewise do not see the officer or GPS position on the inspection record.
- **Logs:** the WebSocket URL carries the access token in its query string, so the load-balancer config
  logs the path only; any proxy you add must do the same.

### 5.4 Audit trail

Logins (success, failure, lockout, blocked), the two-step stages, logouts, replayed refresh tokens, every
password event, account lifecycle (registration, officer creation, approval, suspension) and every report
download. Passwords, codes and tokens are never recorded. Writing is best-effort — a logging failure can't
break a request. Admins read it at **Admin → Audit log**; the API has no way to edit or delete a record,
and the TTL index removes records only after the retention period.

### 5.5 Known limits (stated plainly)

1. **Certificate authenticity is a database lookup, not a cryptographic signature.** The QR and the
   certificate number resolve to a record on the public page. A forged PDF cannot pass the check unless
   it carries a real number, but the PDF itself is not digitally signed. Digital signing (e.g. a DSC/eSign
   flow) would be a separate piece of work.
2. **Client IP trust.** The app uses the first address in `X-Forwarded-For`. Behind a proxy that does not
   overwrite that header, a client can choose its own "IP" and weaken per-IP limits. The supplied nginx
   config overwrites it; on any other host, confirm it does.
3. **Owners don't have 2-step verification** (it's mandatory for officers/admin only).
4. **No CAPTCHA** on forgot-password; signup OTP and reset are rate-limited per IP and per address instead.
5. **First-time officer enrolment is protected by the temporary password alone**, so hand it over through
   a secure channel; an admin can **Reset 2-step** if someone is locked out.
6. **Email is the only verified channel, and the only notification channel.** SMS/WhatsApp alerts and
   mobile-number OTP are deferred until funding allows (roadmap #11).
7. **Not formally audited.** No external penetration test or CERT-In-empanelled audit has been done; GIGW 3.0
   and DPDP Act compliance, and hosting on a NIC/MeitY-empanelled cloud, are outside what this repository
   can provide.

---

## 6. Deployment

### 6.1 Reference topology (what `render.yaml` describes)

| Piece | Service | Notes |
|---|---|---|
| Frontend | Render static site (`maapsetu-web`) | `npm ci && npm run build`; hashed assets cached 1 year, `index.html`/`sw.js` never |
| Backend | Render web service from `backend/Dockerfile` (`maapsetu-api`) | non-root image, 2 uvicorn workers, health check `/api/v1/health` |
| Database | MongoDB Atlas | connection string in `MONGO_URI` (not in the repo) |
| Files | Cloudinary | `CLOUDINARY_*` |
| Mail | Brevo HTTPS API (preferred on Render) or SMTP | |
| Redis | Render Key Value / any Redis | `REDIS_URL`; required once there is more than one instance |
| Worker | Embedded by default; dedicated service optional (paid plan) | `EMBEDDED_WORKER=false` when separate |

The frontend and API are on different `onrender.com` subdomains, which is cross-site, hence
`COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` in the blueprint. Safari and some privacy browsers block
cross-site cookies regardless; serving both from one domain (or proxying `/api` through the frontend host)
avoids that.

### 6.2 First deployment

1. Create the Atlas cluster, a DB user, and allow the host's IP **(infra)**.
2. Generate three secrets: `openssl rand -hex 32` for each of `JWT_SECRET`, `OTP_PEPPER`,
   `MFA_ENCRYPTION_KEY`. **Never change `MFA_ENCRYPTION_KEY` afterwards** — every enrolled officer would
   need a 2-step reset. Use identical values on every instance and the worker.
3. Deploy via the Render Blueprint (or build the Docker image elsewhere). Set `ENVIRONMENT=production`,
   `MONGO_URI`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_LOGIN_URL`, `FRONTEND_BASE_URL`, `FRONTEND_VERIFY_URL`,
   Cloudinary and mail credentials. The app refuses to start if the production guards in §5.1 fail.
4. Seed reference data and the first admin, from a shell with the same environment:
   `python seed_geo.py` then `python seed_super_admin.py`.
5. Open `/api/v1/health`: expect `"status":"ok"`, `"db":true`, and `"embedded_worker":true` (or a running
   dedicated worker).
6. Sign in as the admin, enrol the authenticator, **save the recovery codes**, then create officers.
7. Set the frontend's `VITE_API_BASE_URL` and `VITE_SITE_URL` for the real domains.

### 6.3 Scaling

Covered in full in [`deployment-scaling.md`](deployment-scaling.md). The short version: set `REDIS_URL`,
give every instance the same three secrets, put a load balancer in front that overwrites
`X-Forwarded-For`, passes WebSockets and health-checks `/api/v1/health`, and size Atlas's connection limit
for `instances × workers × 50`. `docker-compose.scale.yml` rehearses this locally (nginx + 3 backends +
worker + Redis). Autoscaling, a CDN and read replicas are provider features; the repo supplies correct
application behaviour and templates **(template — not run against that provider)**.

### 6.4 CI/CD

GitHub Actions on every push/PR to `main`: backend `ruff` + `pytest` (against `mongomock`, no live
database), frontend lint + type-check + build, backend Docker image build, compose-file validation. A
deploy job runs on `main` only after all pass, and only if the repository secrets
`RENDER_DEPLOY_HOOK_URL` / `VERCEL_DEPLOY_HOOK_URL` exist. Set Render's Auto-Deploy to *Off* (or *After CI
Checks Pass*), otherwise it deploys on every push regardless of test results. Dependabot keeps dependencies
current.

### 6.5 Operations

| Task | How |
|---|---|
| Is it healthy? | `GET /api/v1/health` (`db`, `embedded_worker`) |
| Forgotten super-admin password | `python seed_super_admin.py` (rotates it, signs the account out everywhere) |
| Lost authenticator (admin) | `python reset_mfa.py <email>`; for an officer, an admin uses **Reset 2-step** |
| Rotate `JWT_SECRET` | Signs everyone out; keep `MFA_ENCRYPTION_KEY` set separately first, or officers lose their authenticators |
| Certificate PDF URLs wrong | `python fix_certificate_pdf_urls.py` |
| Remove demo data | `python purge_seed_data.py` |
| Check abuse protection / WebSockets | `python burst_test.py`; `python ws_listener.py <port> <token>` |
| Backups | Atlas feature **(infra)** — set up and *test a restore* before going live |

### 6.6 Pre-launch checklist

- [ ] `ENVIRONMENT=production`, `COOKIE_SECURE=true`, real `CORS_ALLOWED_ORIGINS`
- [ ] Random 32+ character `JWT_SECRET`; dedicated `MFA_ENCRYPTION_KEY` and `OTP_PEPPER`
- [ ] `COOKIE_SAMESITE=none` if the frontend and API are on different sites
- [ ] `REDIS_URL` set if more than one worker or instance runs
- [ ] Atlas: IP allow-list narrowed (remove `0.0.0.0/0`), TLS enforced, least-privilege DB user, backups tested
- [ ] A WAF/CDN in front, forwarding the real client IP and bypassing cache for `/api/*` and `/ws/*`
- [ ] Mail provider's sender address verified (a bad sender makes every email fail)
- [ ] Super admin enrolled, recovery codes stored safely offline
- [ ] Officer accounts created; each has enrolled an authenticator and kept recovery codes
- [ ] Field-tested on real phones: install, QR scan, GPS, offline inspection and sync **(not verified in this repo)**

---

## 7. Testing

`pytest` against `mongomock` (no live database): auth hardening, password recovery, two-step verification,
audit trail and viewer, officer scoping, inspections (GPS, idempotency, form rules), scheduling,
re-verification, validity, oversight, search and report export, documents and profile, owner email
notifications, certificate pipeline, WebSocket scoping, and production startup guards. Frontend: `eslint`,
`tsc -b`, `vite build`. The changelog records the latest counts per feature; run the suites before relying
on any number written in a document.

What tests here **cannot** tell you: behaviour against real MongoDB/Redis/Cloudinary/mail providers, in real
browsers, and on real devices. Treat those as manual checks.

---

## 8. Extending the system

- **A new role-scoped list:** add the route with `role_required()`, apply the shared jurisdiction filter,
  reuse the search helpers so exports match what the screen shows, and add a scoping test.
- **A new owner email:** add a template function and a `notify_*` caller with a dedupe key (see the README's
  email table).
- **A new instrument type:** add it to the controlled list, its inspection form in
  `config/inspection_forms.py`, and its specs; an admin can then set its validity period in the app.
- **A new status:** change `services/status_transition.py` and the `$jsonSchema` enum together.

---

## 9. Roadmap items outside the repository's reach

| Item | Why it isn't done | What it needs |
|---|---|---|
| SMS / WhatsApp alerts and mobile-number OTP (#11) | Needs a paid messaging provider (e.g. Twilio) | Funding; then the OTP flow used for email can be reused for phone numbers |
| Real device testing | Needs phones in the field | A pilot with officers |
| Security audit, hosting empanelment, GIGW/DPDP | Organisational, not code | CERT-In-empanelled auditor; NIC/MeitY cloud |
| Digitally signed certificates | Needs a signing authority/eSign integration | A policy decision, then integration |

---

## 10. What this document does not cover

Per-endpoint request/response shapes (see `api-contract.md`), the exact text of every email (see
`email_templates.py`), the UI design system, and anything about a specific production environment — this
repository has no record of one.
