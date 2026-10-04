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

## Done in code — second pass (deploy-blocker cleanup)

The items below were the "still open" list from the first pass. All seven
are now addressed (five in code, two are infra-only and can't be — see the
Infra-only section, which now has concrete steps instead of just a
checkbox).

- **CORS hardcoded to `localhost:5173`** — now driven by `CORS_ALLOWED_ORIGINS`,
  a comma-separated env var (`app/config/settings.py`, used in `main.py`).
  Defaults to the Vite dev origin so local dev/CI is unaffected. **You still
  need to set this to your real deployed frontend origin(s) before
  deploying** — see "Before deploying" below; the app now refuses to start
  in production if you don't.
- **`/__dev/db-info` debug route, unauthenticated** — no longer just
  "present but should be removed": it's conditionally registered in
  `main.py` and genuinely doesn't exist as a route at all when
  `ENVIRONMENT=production` (won't show up in OpenAPI, can't be hit
  regardless of headers/auth). Unauthenticated access is left as-is for
  `ENVIRONMENT=development` since it's a useful local debugging aid and
  never reachable in prod.
- **No startup guard against the `JWT_SECRET` dev default** — `app/config/settings.py`
  now raises `RuntimeError` at import time (before uvicorn accepts any
  connections) if `ENVIRONMENT=production` and `JWT_SECRET` is empty, is
  either known placeholder value, or is under 32 characters. Same pattern
  added for `COOKIE_SECURE` (refuses to start in production with the
  refresh cookie insecure) and for `CORS_ALLOWED_ORIGINS` (refuses to start
  in production with no real origin configured, or `*`).
- **DDoS middleware was single-worker-aware only** — `app/middleware/ddos_protection.py`
  now delegates its state (sliding-window request log, block list, offense
  counts) to a pluggable store (`app/middleware/ddos_store.py`):
  `InMemoryDDoSStore` (original behaviour, single-process only) or
  `RedisDDoSStore` (sorted-set sliding window + TTL'd keys, shared across
  every worker/container). Selected automatically based on whether
  `REDIS_URL` is set. Without `REDIS_URL`, the app still runs fine — it
  just logs a startup warning that `--workers 2` means each worker enforces
  its own independent threshold, exactly as before.
- **MFA/TOTP, RS256 signing, Redis blacklist** — still explicitly
  out-of-scope, unchanged from the first pass. Left here for visibility;
  revisit if judges specifically probe auth depth.

## Done in code — password recovery & session security pass

**Password policy** (`app/utils/validators.py`, mirrored in `frontend/src/lib/validation.ts`)
- 8–64 characters with an uppercase letter, a lowercase letter, a digit and a special character; ~45 very common passwords (e.g. `Password@123`) rejected. Applies to register, change-password and reset-password — **not** to login, so older accounts still sign in. The 64-char cap keeps bcrypt inside its 72-byte limit.
- `seed_super_admin.py` validates `SUPER_ADMIN_PASSWORD` against the same policy.

**Forgot password** (`POST /auth/forgot-password`, `POST /auth/reset-password`)
- Reuses the OTP system (separate `password_reset` purpose, so a signup-verification proof can never unlock a reset). 6-digit HMAC-hashed code, 10-minute expiry, single-use, 5 attempts — the attempt counter is incremented atomically *before* comparing, so parallel guesses can't exceed the cap.
- Anti-enumeration: identical `200 {"sent": true}` for unknown emails, cooldowns and officer/admin accounts; the email is sent in a background task so timing doesn't leak either. One generic `400` for every reset failure. Per-account 60 s cooldown on top of the per-IP rate limit.
- Success revokes every session (token_version bump + all refresh tokens), clears any lockout, and emails a "password changed" notice.

**Officer / admin accounts (`SELF_SERVICE_AUTH_ROLES = {"owner"}`)**
- `lmo`, `gatc`, `admin` get no self-service reset: no code is sent, and the reset endpoint refuses them even with a valid code (defence in depth). A hijacked mailbox is not enough to take over a government account.
- Officers are reset by an admin: `POST /admin/users/{id}/reset-password` → one-time temp password (shown once + emailed), forced change at next login, sessions revoked, lockout cleared, pending reset codes deleted. Admin accounts can't be reset through the API; the operator re-runs `seed_super_admin.py`, which now also revokes that account's sessions.

**Remember me**
- Owner accounts only; the server ignores the flag for officers/admin and reports the real outcome in the response, which the frontend trusts over its own checkbox. 30-day sliding refresh cookie (`REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS`); otherwise a browser-session cookie. Rotation preserves the choice.

**Session handling**
- `change-password` now signs the account out of every other session (token_version bump + all refresh tokens revoked) and issues a fresh token + cookie to the device that made the change.
- "Password changed" email after every successful change/reset (IST timestamp, never the password).

**Two-step verification (TOTP) — mandatory for `lmo`, `gatc`, `admin`** (`MFA_REQUIRED_ROLES`)
- After the password is accepted, `/auth/login` returns only a 10-minute `mfa_token` — no access token, refresh cookie or user data. The session starts in `/auth/mfa/verify` (6-digit code or one-time recovery code) or, for an account with no authenticator yet, `/auth/mfa/confirm-setup` (scan QR → confirm one code → 8 recovery codes shown once).
- The `mfa_token` is a JWT of type `mfa` bound to one step; `decode_access_token` rejects it as a Bearer token, it's refused for the wrong step, expires, and dies if the password changes or sessions are revoked (`token_version`).
- TOTP is RFC 6238 (SHA-1 / 6 digits / 30 s / ±1 step), implemented with the standard library and tested against the RFC's published vectors. An accepted time-step can't be reused (atomic `mfa_last_step` claim, so two simultaneous submissions can't both win); recovery codes are consumed with an atomic `$pull`.
- Wrong codes feed the same failed-attempt counter and lockout as wrong passwords. The counter is **not** cleared by the password step — only by a completed second step — so knowing the password never buys unlimited code guesses.
- Authenticator secrets are encrypted at rest with Fernet (`cryptography`; key from `MFA_ENCRYPTION_KEY`, else derived from `JWT_SECRET`); recovery codes are stored only as keyed HMAC hashes.
- Refresh tokens carry `mfa_verified`; `/auth/refresh` requires it for officer/admin accounts, so sessions can't be renewed from a password alone and officer sessions that predate this feature are retired (they sign in again). The mark is preserved by `change-password`.
- Recovery paths: admin → `POST /admin/users/{id}/reset-mfa` (officers only); operator → `python reset_mfa.py <email>` for the super admin (not exposed via the API, so a hijacked admin session can't strip another admin's second factor).
- **Known limitation:** first-time enrolment is protected only by the temporary password, so an attacker who intercepted it could enrol first. Hand temp passwords over securely; "Reset 2-step" recovers the account. Access tokens issued before deployment stay valid for their remaining ≤15 minutes.

**Account lifecycle & session fixes**
- Audit events for registration (including blocked self-registration as officer/admin), officer creation, approve and suspend (see `docs/api-contract.md` → "Audit log").
- Suspending an officer (`/reject`) now ends their sessions immediately; `/auth/refresh` also refuses accounts that are no longer `active`. Before this, a suspended officer could stay signed in indefinitely by letting the browser renew the session.

**OTP abuse limits & rate-limit scaling**
- `POST /otp/send` is limited per IP (5 / 15 min) **and** per address (one code per 60 s, `OTP_SEND_COOLDOWN_SECONDS`) — the per-address cooldown holds no matter how many IPs ask, and applies to every address equally so it can't be used to learn who has an account. The email is sent in a background task. `POST /otp/verify` is limited too (15 / 15 min / IP). Both are audit-logged (`signup_otp_requested`).
- Rate-limit counters (slowapi) are stored in Redis when `REDIS_URL` is set, so limits hold across uvicorn workers and container instances (before, "15 per 15 min" silently became 15 × workers × instances). If Redis is unreachable the limiter degrades to per-process memory instead of erroring — covered by a test.

**Audit-log viewer** (`GET /admin/audit-logs`, Admin → Audit log)
- Admin-only, read-only (no edit/delete route exists), filterable by event / outcome / role / email text / date, paginated. Search text is matched literally, never as a pattern. A source-scanning test fails if a `log_event("…")` name is added without being listed for the viewer's filter. Admin-initiated records carry `actor_email`.

**Read replicas** (`MONGO_READ_PREFERENCE`)
- Opt-in `secondaryPreferred` reads for staleness-tolerant endpoints only (geo, dashboards, public certificate verification, audit viewer). Sign-in, token/user/suspension checks and read-your-writes lists always use the primary; a test fails if any other module starts using `read_replica`.

**Audit trail** (`app/services/audit.py`, collection `audit_logs`, logger `app.audit`)
- Login success / failure / blocked (locked, pending, rejected), logout, logout-all, replayed refresh tokens, and all password events including admin-initiated resets. Never records passwords, codes or tokens; best-effort so it can't break a request. TTL-indexed (`AUDIT_LOG_RETENTION_DAYS`, default 365, minimum 180). Event list: `docs/api-contract.md` → "Audit log".
- This is an application-level log and does not need an M10+ Atlas tier; the Atlas-side audit logging listed under Infra-only is still a separate, infra-level item.

**Still open from this pass**
- No CAPTCHA on forgot-password; no self-service "regenerate recovery codes" screen (an admin resets an officer's two-step verification instead); two-step verification isn't offered to owner accounts.
- Safari/privacy browsers block third-party cookies, so "Remember me" may not persist while the frontend and API are on different domains — proxy `/api` through the frontend host or serve both from one domain.

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

Nothing in this repo can do these for you — code can't reach into Atlas's
or Cloudflare's dashboards. Concrete steps for the two flagged as "likely
still open":

**Atlas Network Access (currently likely `0.0.0.0/0`)**
1. Get the deploy host's outbound IP(s). Render/Railway: shown on the
   service's "Settings" page (some plans use a pool of IPs — check whether
   your plan gives a static IP; if not, you either need a paid tier with
   static outbound IPs, or a NAT/proxy with a fixed IP in front of egress).
2. Atlas dashboard → **Network Access** → **Add IP Address** → enter that
   IP (or CIDR range) with a clear description (e.g. "Render prod backend").
3. Remove the `0.0.0.0/0` entry once the real entry is confirmed working —
   don't leave both, or the whitelist is a no-op.
4. Re-deploy and hit `/api/v1/health` — if `"db": false`, the new IP entry
   isn't right yet (check Atlas's connection logs for the rejected IP).

**Cloudflare / WAF in front of the app**
1. Point the frontend's domain (and the API's, if it has its own subdomain
   e.g. `api.example.com`) through Cloudflare (or your host's built-in
   equivalent, e.g. Render/Railway's own edge) — this is a DNS + dashboard
   change, not a code change.
2. Enable Cloudflare's "Under Attack" mode or the free WAF ruleset if
   volumetric traffic becomes a real concern — the in-repo DDoS middleware
   (`app/middleware/ddos_protection.py`) is a second, app-level layer, not
   a substitute for this; it can't absorb a real distributed flood.
3. Once behind Cloudflare, make sure the app trusts Cloudflare's
   `CF-Connecting-IP` (or `X-Forwarded-For`) header for the *real* client
   IP — otherwise `app/middleware/ddos_protection.py` sees Cloudflare's IP
   for every request and the per-IP logic stops meaning anything. Configure
   the host/proxy layer to pass the original client IP through as
   `X-Forwarded-For` (which `_client_ip()` already reads).

Also still infra-only, unchanged from the first pass:
- Atlas: confirm TLS enforced + encryption-at-rest (default, but verify on your cluster)
- Atlas: separate least-privilege DB user per service (currently likely one shared user)
- Atlas audit logging / access alerts — needs M10+ (paid) tier; skip on a free-tier hackathon cluster
- Automated backups + a tested restore — set up once you're on a tier that supports it
- HTTPS redirect + TLS termination — handled by whichever host you deploy to (Render/Railway/Vercel); once that's live, set `COOKIE_SECURE=true`
- Terraform/Pulumi, ELK/Datadog, Prometheus+Grafana, UptimeRobot — full observability/IaC stack, reasonable next step post-hackathon, not before

## Before deploying (checklist)

- [ ] Set `COOKIE_SECURE=true` once served over HTTPS — **the app now refuses to start in production without this**
- [ ] Set `CORS_ALLOWED_ORIGINS` to your real deployed frontend origin(s) — **the app now refuses to start in production with the `localhost:5173` default or `*`**
- [ ] Set a real, random, 32+ char `JWT_SECRET` (not `dev_secret_change_me` or the `.env.example` placeholder) — **the app now refuses to start in production without this**
- [ ] Set `ENVIRONMENT=production` in the deploy host's env vars — this is what turns on all three guards above, and what removes `/__dev/db-info`
- [ ] Set `MFA_ENCRYPTION_KEY` to a dedicated long random value (`openssl rand -hex 32`) so authenticator secrets stay decryptable if `JWT_SECRET` is ever rotated — **losing or changing it makes every stored authenticator unusable** (officers would need a reset)
- [ ] After deploying, officers and the super admin set up an authenticator at their next sign-in (existing officer sessions are retired); make sure each of them gets their recovery codes
- [ ] Set `OTP_PEPPER` to a long random value (`openssl rand -hex 32`) — it also hashes password-reset codes, and without it a public default is used
- [ ] If the frontend and API are on different sites (e.g. Vercel + Render): set `COOKIE_SAMESITE=none` together with `COOKIE_SECURE=true`, or the refresh cookie (and "Remember me") won't work
- [ ] Set `REDIS_URL` if running with `--workers > 1` or multiple containers — otherwise the DDoS middleware's per-IP threshold is effectively multiplied by however many workers/instances are running (the app still starts and runs without it — just logs a warning)
- [ ] Whitelist the deploy host's IP in Atlas Network Access, and remove `0.0.0.0/0`
- [ ] Put the deployed app behind Cloudflare (or host-equivalent) and confirm `X-Forwarded-For`/`CF-Connecting-IP` reaches the app correctly

## Pre-existing issues surfaced while wiring CI (not touched — not part of this pass)

`npm run lint` currently fails on 2 pre-existing errors, unrelated to this hardening work:
- `pages/auth/Register.tsx:109` — `no-explicit-any`
- `pages/owner/RegisterInstrument.tsx:47` — `'React' is not defined`

These will fail the new `frontend` CI job until fixed by whoever owns those files.
