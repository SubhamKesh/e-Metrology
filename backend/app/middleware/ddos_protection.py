"""
Global DDoS/DoS protection: per-IP sliding-window rate limiting with
temporary auto-blocking for IPs that exceed a threshold.

This is separate from slowapi (rate_limit.py), which only guards
/login and /register against credential brute-forcing. This middleware
runs in front of EVERY route and protects against a single IP hammering
the API generally (scraping, flooding, misbehaving client, etc).

Design notes / limitations (read before deploying):
- State lives in a pluggable store (see ddos_store.py): Redis when
  REDIS_URL is configured, otherwise an in-process dict.
    * With the in-memory store, each uvicorn worker process tracks its own
      counts independently. With `--workers 2` (see Dockerfile), an IP
      effectively gets ~2x the configured threshold, since it's coin-flipped
      across workers. Set REDIS_URL to fix this -- see ddos_store.py.
    * The in-memory store's state resets on restart/redeploy; Redis
      persists across app restarts (not across a Redis restart, unless
      Redis itself is configured with persistence).
- This is app-level DoS protection, not real DDoS mitigation. A
  large-scale volumetric DDoS (thousands of source IPs) has to be
  stopped upstream (Cloudflare / AWS Shield / a WAF) -- no amount of
  code in this process can absorb that kind of traffic. This
  middleware's job is the more modest one of: stop a single misbehaving
  IP from hammering this API and starving out real users.
- Trusts X-Forwarded-For's first hop if present (for when this sits
  behind a reverse proxy/load balancer), else falls back to the raw
  connection IP. If deployed behind a proxy that doesn't set this
  header, every request will appear to come from the proxy's IP --
  configure the proxy to set X-Forwarded-For correctly.
"""
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config.settings import REDIS_URL
from app.middleware.ddos_store import build_store

# --- Tunables -----------------------------------------------------------
# Sliding window: if an IP makes more than WINDOW_MAX_REQUESTS requests
# within WINDOW_SECONDS, it's considered abusive.
WINDOW_SECONDS = 10
WINDOW_MAX_REQUESTS = 60  # ~6 req/sec sustained before it's flagged

# How long a flagged IP is blocked before it gets another chance.
BLOCK_DURATION_SECONDS = 5 * 60  # 5 minutes

# Repeat offenders (blocked more than this many times) get a much longer
# block -- deters a client that just waits out the short block and resumes.
REPEAT_OFFENDER_THRESHOLD = 3
REPEAT_OFFENDER_BLOCK_SECONDS = 60 * 60  # 1 hour

# Built once at import time. Picks Redis when REDIS_URL is configured (and
# the `redis` package is installed), otherwise the original in-memory dict --
# see ddos_store.build_store() for the fallback/logging logic.
_store = build_store(REDIS_URL)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry is the original client; the rest are proxy hops.
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def ddos_protection_middleware(request: Request, call_next):
    now = time.time()
    ip = _client_ip(request)

    blocked, blocked_until = await _store.is_blocked(ip, now)
    if blocked:
        retry_after = int(blocked_until - now)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. You have been temporarily blocked."},
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    if await _store.record_and_check(ip, now, WINDOW_SECONDS, WINDOW_MAX_REQUESTS):
        offense_count = await _store.bump_offense_count(ip)
        if offense_count >= REPEAT_OFFENDER_THRESHOLD:
            duration = REPEAT_OFFENDER_BLOCK_SECONDS
        else:
            duration = BLOCK_DURATION_SECONDS
        await _store.block(ip, now, duration)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. You have been temporarily blocked."},
            headers={"Retry-After": str(duration)},
        )

    return await call_next(request)
