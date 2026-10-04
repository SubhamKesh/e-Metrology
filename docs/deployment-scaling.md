# Deployment & Scaling Guide

What the code already does for scale, what the repo gives you to rehearse it, and the provider-side settings that only you can switch on. Nothing here changes how the app works with a single instance and no Redis — everything is opt-in.

> **Honest scope.** A repository can't provision a load balancer, autoscaling or a CDN — those live in your hosting provider. This repo provides (a) application code that is *correct* when run as many instances, (b) a tested load-balancer config and a local multi-instance stack to prove it, and (c) configuration/templates for the provider settings. Items marked **(template)** were written from the provider's documented format but **not** run against that provider.

---

## 1. Prerequisite for more than one instance: `REDIS_URL`

All state that must be shared between workers/instances lives in Redis. **Set `REDIS_URL` before running more than one backend worker or instance** (the app logs a warning in production if you don't).

| Shared concern | Without Redis (each process alone) | With `REDIS_URL` |
|---|---|---|
| DDoS / flood counters | threshold multiplied by processes | one shared window |
| **Rate-limit counters** (`/login`, `/register`, `/otp/*`, forgot/reset password, two-step) | "15 per 15 min" really means 15 × workers × instances | one shared count; falls back to per-process memory if Redis is down, rather than failing requests |
| WebSocket notifications | only users connected to the same instance | any instance reaches any user (no sticky sessions needed) |
| Expiry scheduler | every instance runs it | one instance per tick (run-lock) |
| Certificate / email jobs | inline or in a thread | background worker (`python run_worker.py`) |

---

## 2. Load balancer

### Rehearse it locally (`docker-compose.scale.yml`)

```bash
export JWT_SECRET=$(openssl rand -hex 32) OTP_PEPPER=$(openssl rand -hex 32) MFA_ENCRYPTION_KEY=$(openssl rand -hex 32)
docker compose -f docker-compose.scale.yml up --build          # nginx :8080 -> 3 backends, 1 worker, Redis, MongoDB
docker compose -f docker-compose.scale.yml up -d --scale backend=5   # add capacity while it runs
```
Point the frontend at it (`VITE_API_BASE_URL=http://localhost:8080`). Things worth trying: sign in, then watch `docker compose logs backend` — requests spread across replicas; open two browsers as different users and confirm live notifications still arrive (that's the Redis fan-out); hit `/login` with wrong passwords from one machine and confirm the limit is shared across replicas.

### Requirements for *any* load balancer (nginx, Render's, a cloud LB)

`deploy/nginx/nginx.conf` implements all of these and is the reference:

| Requirement | Why |
|---|---|
| **Pass WebSockets through** (`Upgrade`/`Connection` headers, long read timeout) on `/ws/` | live notifications |
| **Overwrite** `X-Forwarded-For` with the real client IP — don't append to a client-supplied value | the app trusts the *first* address for rate limiting, lockout and the audit log; if the proxy appends, an attacker can pick their own "IP" by sending the header |
| Health check on `GET /api/v1/health` | remove unhealthy instances |
| **Don't log query strings on `/ws/`** | the WebSocket URL carries the user's access token (`?token=…`) |
| Request body limit ≥ the app's `MAX_REQUEST_BODY_BYTES` (2 MB) | so clients see the app's JSON error, not a bare 413 |
| Coarse per-IP flood limit | defence in front of the app's own limits |
| No sticky sessions needed | state is in Redis / JWTs |

**Verified:** the nginx config was syntax-checked and run in front of a test server, confirming that a spoofed `X-Forwarded-For` is replaced with the real client IP, WebSocket upgrade headers reach the backend, a `?token=` query string never appears in the access log, the health probe isn't logged, and a 300-request burst from one IP is cut off (66 served, 234 rejected with 429). **Not verified:** the multi-replica DNS round-robin and the Docker stack itself (no Docker where this was written) — CI validates that both compose files parse, but run the stack once yourself.

On **Render**, the platform already provides the load balancer, TLS and the health check (`healthCheckPath` in `render.yaml`); it forwards the client IP in `X-Forwarded-For`. You scale by running more instances (section 3).

---

## 3. Autoscaling

Autoscaling is a provider feature. On **Render** it requires a **paid** web-service plan (the `free` plan in `render.yaml` runs one instance and sleeps when idle). **(template)** — when you upgrade, the relevant additions to `render.yaml` look like this; check the field names against Render's Blueprint reference before applying:

```yaml
services:
  - type: web
    name: maapsetu-api
    plan: standard              # autoscaling needs a paid plan
    scaling:
      minInstances: 2
      maxInstances: 5
      targetCPUPercent: 70
    envVars:
      - key: REDIS_URL          # REQUIRED once there is more than one instance
        fromService:
          type: keyvalue
          name: maapsetu-redis
          property: connectionString

  - type: worker                # certificates + emails
    name: maapsetu-worker
    runtime: docker
    rootDir: backend
    dockerfilePath: ./Dockerfile
    dockerCommand: python run_worker.py
    plan: starter
    envVars:                    # same MONGO_URI, DB_NAME, JWT_SECRET, SMTP_*, CLOUDINARY_*, REDIS_URL as the API

  - type: keyvalue              # Redis
    name: maapsetu-redis
    plan: starter
    ipAllowList: []             # internal connections only
```

Notes: `run_worker.py` is now inside the backend image, so the same Dockerfile serves both the API and the worker. On Atlas, size the cluster's connection limit for `instances × workers × maxPoolSize (50)`.

---

## 4. CDN

The frontend is static, so a CDN is mostly about **cache headers**:

- **Render static site** (`maapsetu-web` in `render.yaml`) is served through Render's CDN; Vercel serves through its own. Both now send `Cache-Control: public, max-age=31536000, immutable` for `/assets/*` (Vite renames these files on every build, so a long cache is safe) and `no-cache` for `index.html` (a new deploy shows up immediately). Vercel's rule is in `frontend/vercel.json`.
- **The API should not be cached by a CDN** — responses are per-user and authenticated. If you put a CDN or WAF (e.g. Cloudflare) in front of the API purely for DDoS absorption, make sure it forwards the real client IP (`X-Forwarded-For` / `CF-Connecting-IP`) and passes WebSockets; set it to *bypass cache* for `/api/*` and `/ws/*`.
- The public certificate-verify endpoint (`GET /certificates/verify/{id}`) already has a server-side read-through cache (300 s) when Redis is on; a short CDN cache for it is possible later but is not configured.

---

## 5. MongoDB read replicas

Set `MONGO_READ_PREFERENCE=secondaryPreferred` (default `primary`) when the database is a replica set (every Atlas cluster, including the free tier, is one; a single standalone `mongod` or the compose `mongo` is not — leave it `primary`).

| Reads from a secondary when available | Always the primary |
|---|---|
| `GET /geo/*` (states, districts) | sign-in, token and user checks (a revoked token or suspended account must take effect immediately) |
| dashboards (counts and aggregates) | every list a user just changed (instruments, applications, inspections — read-your-writes) |
| public certificate verification | everything that writes |
| the audit-log viewer | |

A secondary can trail the primary by a moment (normally well under a second), which is harmless for the left column. The routing is done by `read_replica(collection)` in `app/config/db.py`, applied at the call sites; a test (`test_replica_reads_are_used_only_where_staleness_is_harmless`) fails if any other module starts using it. **Do not** put `readPreference` in `MONGO_URI` — that would send every read, including the security-critical ones, to secondaries.

---

## 6. CI and deploy hooks

`.github/workflows/ci.yml` runs lint → tests → builds → compose-file validation, then a **deploy** job on pushes to `main` *only after everything else passed*. The deploy job does nothing unless you add repository secrets (Settings → Secrets and variables → Actions):

| Secret | Where to get it | Effect |
|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | Render → service → Settings → **Deploy Hook** | triggers a backend deploy |
| `VERCEL_DEPLOY_HOOK_URL` | Vercel → project → Settings → Git → **Deploy Hooks** | triggers a frontend deploy (only needed if you turned off Vercel's Git integration — by default it deploys on its own) |

To make "deploy only if tests pass" true, set Render's **Auto-Deploy** to *Off* (or *After CI Checks Pass*). If it stays *On*, Render deploys on every push regardless of test results and the hook just causes a second deploy.

---

## 7. Checklist before running more than one instance

- [ ] `REDIS_URL` set on the API **and** the worker
- [ ] A worker process is running (`python run_worker.py`), or you accept the in-process fallback
- [ ] `MFA_ENCRYPTION_KEY`, `OTP_PEPPER`, `JWT_SECRET` identical on every instance (a per-instance secret breaks sign-in and two-step)
- [ ] Load balancer overwrites `X-Forwarded-For`, passes WebSockets, health-checks `/api/v1/health`, and doesn't log `/ws/` query strings
- [ ] `MONGO_READ_PREFERENCE=secondaryPreferred` only if the database is a replica set
- [ ] Atlas connection limit ≥ instances × workers × 50
