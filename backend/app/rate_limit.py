"""
Rate limiting via slowapi (Section 1 / Section 5 of the hardening checklist:
"rate limiting specifically on /login and /register").

Kept in its own module (rather than inline in main.py) so routers can do
`from app.rate_limit import limiter, RATE_LIMIT_AUTH` without a circular
import on `app` from main.py.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.settings import REDIS_URL

# Counters live in Redis when REDIS_URL is set, so a limit means the same thing
# no matter how many uvicorn workers or container instances are running. (Kept
# in process memory — the old behaviour — each worker counted separately, so
# "15 per 15 minutes" quietly became 15 x workers x instances behind a load
# balancer.) If Redis becomes unreachable the limiter falls back to per-process
# memory instead of failing requests.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL or "memory://",
    in_memory_fallback_enabled=bool(REDIS_URL),
)

# 15 attempts per 15 minutes per IP, matching the checklist's suggested
# figure. Applied to /login and /register specifically, not globally —
# a global limit belongs at the reverse proxy / gateway layer per the
# checklist's DDoS section, which is an infra concern outside this repo.
RATE_LIMIT_AUTH = "15/15minutes"

# Signup OTP emails. Tighter than the general auth limit because each request
# sends an email to an address the caller may not own. Combined with a
# per-address cooldown (OTP_SEND_COOLDOWN_SECONDS) so many callers can't pile
# onto one inbox either.
RATE_LIMIT_OTP_SEND = "5/15minutes"
