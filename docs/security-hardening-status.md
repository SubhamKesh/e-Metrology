# Security & Scaling Hardening — Implementation Status

Tracks `backend-security-scaling-checklist.md` against what's actually been
implemented in this repo, adapted for the real stack: **FastAPI + PyMongo +
MongoDB Atlas**, not the Node/Express stack the checklist was written for.

## Done in code

**Auth**
- Access tokens shortened to 15 min (`ACCESS_TOKEN_EXPIRES_MINUTES`), down from 7 days
- Refresh tokens: random (not JWT), stored as a SHA-256 hash in `refresh_tokens`, httpOnly + secure + sameSite=strict cookie, TTL-indexed so Mongo auto-expires them
- Refresh token rotation: every `/auth/refresh` call revokes the old token and issues a new one; reuse of a rotated-away token is rejected
- Revocation without Redis: `token_version` field on the user doc, embedded in every access token as `tv` and checked on every request (`middleware/auth.py`). Bump it (`/auth/logout-all`) and every outstanding access token dies instantly, before its natural expiry
- Rate limiting on `/login` and `/register`: 5 attempts / 15 min per IP (`slowapi`)
- Account lockout: exponential backoff (1, 2, 4, 8... min) after 5 failed attempts, tracked per-user in Mongo
- RBAC: already existed (`role_required()`), unchanged

**DB (Mongo/Atlas)**
- Connection pooling limits (`maxPoolSize=50`, `minPoolSize=5`) so this process can't exhaust Atlas's shared connection limit
- `$jsonSchema` validation on `users`, `applications`, `refresh_tokens` — a second, DB-level check independent of Pydantic (moderate level, so it won't break existing documents)

**Breach protection**
- Passwords already bcrypt-hashed (pre-existing, unchanged)
- Secrets already in `.env` / env vars, `.env` already gitignored (pre-existing, unchanged)
- Security headers middleware (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`) — the FastAPI equivalent of helmet.js, since there's no single dominant package for this in Python
- Request body size limit (2MB default, `MAX_REQUEST_BODY_BYTES`)

**Load / health**
- `/api/v1/health` already existed, unchanged
- Dockerfile runs `uvicorn` with `--workers 2` as a first step toward running multiple instances

**DevOps**
- `backend/Dockerfile` — multi-stage, non-root user, HEALTHCHECK
- `docker-compose.yml` — local dev only (backend + Mongo), not the prod deploy shape
- `.github/workflows/ci.yml` — lint (ruff) + test (pytest, against `mongomock`) for backend, lint + type-check + build for frontend, plus a Docker build check
- `.github/dependabot.yml` — weekly pip/npm scans, monthly Actions scans
- New tests: `backend/tests/test_auth_hardening.py` covers lockout, refresh rotation/reuse-rejection, logout-all, security headers, body-size limit

**Frontend (required for the shorter access-token lifetime to actually work)**
- `lib/api.ts`: every request now sends `credentials: "include"` so the httpOnly refresh cookie is actually sent/received
- Transparent refresh-on-401: a 401 on any non-`/auth/*` request triggers one silent `POST /auth/refresh` + retry before falling back to clearing the token and bouncing to `/login` — without this, the 15-min access token would log everyone out every 15 minutes
- Concurrent 401s share a single in-flight refresh call (no thundering-herd of refresh requests if several API calls 401 at once)
- `AuthContext.logout()` now calls `POST /auth/logout` (best-effort) to revoke the refresh token server-side, not just clear localStorage
- No UI/visual changes — this is all inside the existing fetch layer



- **MFA / TOTP** — real feature work; skipped given hackathon timeline. Revisit if judges specifically probe auth depth.
- **RS256 signing** — only pays off with multiple independent services verifying tokens; this is a single monolith, so HS256 is fine for now.
- **Redis-backed blacklist** — not needed: `token_version` gives the same instant-revocation property without adding Redis as a new infra dependency.

## Infra-only — needs doing on the Atlas / hosting dashboard, not in this repo

Nothing in this repo can do these for you:
- Atlas Network Access: whitelist deployment server IP(s), turn off `0.0.0.0/0`
- Atlas: confirm TLS enforced + encryption-at-rest (default, but verify on your cluster)
- Atlas: separate least-privilege DB user per service (currently likely one shared user)
- Atlas audit logging / access alerts — needs M10+ (paid) tier; skip on a free-tier hackathon cluster
- Automated backups + a tested restore — set up once you're on a tier that supports it
- Cloudflare / AWS Shield / WAF in front of the deployed app
- HTTPS redirect + TLS termination — handled by whichever host you deploy to (Render/Railway/Vercel); once that's live, set `COOKIE_SECURE=true`
- Terraform/Pulumi, ELK/Datadog, Prometheus+Grafana, UptimeRobot — full observability/IaC stack, reasonable next step post-hackathon, not before

## Before deploying (checklist)

- [ ] Set `COOKIE_SECURE=true` once served over HTTPS
- [ ] Tighten CORS `allow_origins` in `main.py` away from `localhost:5173`
- [ ] Set a real `JWT_SECRET` (not the `dev_secret_change_me` default) in prod env vars
- [ ] Whitelist the deploy host's IP in Atlas Network Access

## Pre-existing issues surfaced while wiring CI (not touched — not part of this pass)

`npm run lint` currently fails on 2 pre-existing errors, unrelated to this hardening work:
- `pages/auth/Register.tsx:109` — `no-explicit-any`
- `pages/owner/RegisterInstrument.tsx:47` — `'React' is not defined`

These will fail the new `frontend` CI job until fixed by whoever owns those files.
