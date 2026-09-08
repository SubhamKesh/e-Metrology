"""
Rate limiting via slowapi (Section 1 / Section 5 of the hardening checklist:
"rate limiting specifically on /login and /register").

Kept in its own module (rather than inline in main.py) so routers can do
`from app.rate_limit import limiter, RATE_LIMIT_AUTH` without a circular
import on `app` from main.py.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# 5 attempts per 15 minutes per IP, matching the checklist's suggested
# figure. Applied to /login and /register specifically, not globally —
# a global limit belongs at the reverse proxy / gateway layer per the
# checklist's DDoS section, which is an infra concern outside this repo.
RATE_LIMIT_AUTH = "5/15minutes"
