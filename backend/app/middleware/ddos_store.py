"""
Storage backends for the DDoS-protection middleware (ddos_protection.py).

Two implementations of the same small interface:

- InMemoryDDoSStore: a plain in-process dict, like the original
  implementation. Correct for a single worker process; with uvicorn's
  `--workers N` (or multiple deployed containers) each worker has its own
  copy of the state, so a single IP effectively gets ~N x the configured
  threshold before any one worker blocks it.
- RedisDDoSStore: same logic, backed by Redis, so every worker/instance
  shares one view of each IP's request history and block status. This is
  the fix for the "single-worker-aware" limitation — selected automatically
  whenever REDIS_URL is configured (see app/config/settings.py).

Both expose the same async interface so `ddos_protection.py` doesn't need
to know which one it's talking to.
"""
import time
import uuid
from collections import defaultdict, deque
from typing import Optional, Tuple


class InMemoryDDoSStore:
    """Original behaviour: a plain in-process dict. Only correct with a
    single worker process and no horizontal scaling."""

    def __init__(self):
        # ip -> deque of request timestamps within the current window
        self._request_log: dict[str, deque] = defaultdict(deque)
        # ip -> unix timestamp the block expires at
        self._blocked_until: dict[str, float] = {}
        # ip -> number of times this ip has been blocked (repeat-offender escalation)
        self._offense_count: dict[str, int] = defaultdict(int)

    async def is_blocked(self, ip: str, now: float) -> Tuple[bool, float]:
        expiry = self._blocked_until.get(ip)
        if expiry is None:
            return False, 0.0
        if now >= expiry:
            del self._blocked_until[ip]
            return False, 0.0
        return True, expiry

    async def record_and_check(self, ip: str, now: float, window_seconds: int, max_requests: int) -> bool:
        """Logs this request and returns True if the IP just crossed the
        threshold and should be newly blocked."""
        log = self._request_log[ip]
        log.append(now)
        cutoff = now - window_seconds
        while log and log[0] < cutoff:
            log.popleft()
        return len(log) > max_requests

    async def block(self, ip: str, now: float, duration: float) -> None:
        self._blocked_until[ip] = now + duration
        self._request_log.pop(ip, None)

    async def bump_offense_count(self, ip: str) -> int:
        self._offense_count[ip] += 1
        return self._offense_count[ip]


class RedisDDoSStore:
    """Redis-backed version of the same logic, shared across every worker
    process / container talking to the same Redis instance.

    Uses a sorted set per IP for the sliding window (score = request
    timestamp) and plain keys with TTLs for block state and offense counts,
    so Redis itself garbage-collects everything without a background job.
    """

    # Keep offense counts around long enough to matter for repeat-offender
    # escalation, but don't let them live forever.
    _OFFENSE_TTL_SECONDS = 24 * 60 * 60

    def __init__(self, redis_url: str):
        # Imported lazily so a deployment that never sets REDIS_URL doesn't
        # need the `redis` package installed at all.
        from redis.asyncio import Redis

        self._redis: Redis = Redis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def _log_key(ip: str) -> str:
        return f"ddos:log:{ip}"

    @staticmethod
    def _blocked_key(ip: str) -> str:
        return f"ddos:blocked:{ip}"

    @staticmethod
    def _offense_key(ip: str) -> str:
        return f"ddos:offenses:{ip}"

    async def is_blocked(self, ip: str, now: float) -> Tuple[bool, float]:
        val = await self._redis.get(self._blocked_key(ip))
        if val is None:
            return False, 0.0
        expiry = float(val)
        if now >= expiry:
            # Shouldn't normally happen (the key has its own TTL), but keep
            # behaviour identical to the in-memory store just in case.
            await self._redis.delete(self._blocked_key(ip))
            return False, 0.0
        return True, expiry

    async def record_and_check(self, ip: str, now: float, window_seconds: int, max_requests: int) -> bool:
        key = self._log_key(ip)
        cutoff = now - window_seconds
        # Unique member per request (timestamp alone can collide under
        # load) so ZADD never overwrites a distinct request.
        member = f"{now}:{uuid.uuid4().hex}"

        pipe = self._redis.pipeline(transaction=True)
        pipe.zadd(key, {member: now})
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        # Bound the key's own lifetime so an IP that goes quiet doesn't
        # leave a forever-growing set of keys behind in Redis.
        pipe.expire(key, window_seconds * 2)
        results = await pipe.execute()
        count = results[2]
        return count > max_requests

    async def block(self, ip: str, now: float, duration: float) -> None:
        expiry = now + duration
        await self._redis.set(self._blocked_key(ip), expiry, ex=int(duration) + 5)
        await self._redis.delete(self._log_key(ip))

    async def bump_offense_count(self, ip: str) -> int:
        key = self._offense_key(ip)
        count = await self._redis.incr(key)
        await self._redis.expire(key, self._OFFENSE_TTL_SECONDS)
        return count


def build_store(redis_url: Optional[str]):
    """Returns a RedisDDoSStore if redis_url is set and the `redis` package
    is importable, otherwise falls back to InMemoryDDoSStore. Logs which one
    it picked so a misconfiguration (REDIS_URL set but package missing)
    isn't silent."""
    import logging

    logger = logging.getLogger("maapsetu")

    if redis_url:
        try:
            store = RedisDDoSStore(redis_url)
            logger.info("DDoS protection: using Redis-backed shared state (REDIS_URL configured).")
            return store
        except ImportError:
            logger.warning(
                "REDIS_URL is set but the `redis` package isn't installed "
                "(add `redis` to requirements.txt). Falling back to "
                "per-worker in-memory DDoS protection state."
            )
    else:
        logger.warning(
            "REDIS_URL is not set: DDoS protection is using per-worker "
            "in-memory state. Fine for a single worker/local dev; with "
            "uvicorn --workers N or multiple containers, each instance "
            "enforces its own independent threshold. Set REDIS_URL in "
            "production to share state across all of them."
        )
    return InMemoryDDoSStore()
