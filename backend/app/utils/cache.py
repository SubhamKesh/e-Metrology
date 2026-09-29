"""
Small read-through cache for expensive queries whose result is the same
for every caller (or cacheable per a simple key) and doesn't need to be
perfectly fresh to the second — the public certificate-verify lookup and
the admin dashboard's national aggregation are the two current uses.

Deliberately a plain *synchronous* Redis client, like expiry_cron.py's
lock and unlike the async client in middleware/ddos_store.py /
services/notifications.py — every current caller here is a plain `def`
route (FastAPI runs those in a threadpool, not the asyncio event loop),
so there's no running loop to await against.

Without REDIS_URL configured, get()/set() are no-ops (get() always misses,
set() does nothing) — callers always fall through to querying the database
directly, same graceful-degradation pattern as everywhere else Redis is
optional in this project. Caching is a performance optimization; it should
never be a hard dependency for correctness.
"""
import json
import logging

from app.config.settings import REDIS_URL

logger = logging.getLogger("maapsetu")

_redis = None


def _get_redis():
    global _redis
    if _redis is None and REDIS_URL:
        import redis as redis_sync

        _redis = redis_sync.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def cache_get(key: str):
    """Returns the cached value (already JSON-decoded), or None on a
    cache miss / no Redis configured / any Redis error. A cache failure
    should degrade to "just query the database," never raise."""
    redis = _get_redis()
    if redis is None:
        return None
    try:
        raw = redis.get(key)
    except Exception:
        logger.warning("Cache read failed for key=%s; falling through to the database.", key, exc_info=True)
        return None
    return json.loads(raw) if raw is not None else None


def cache_set(key: str, value, ttl_seconds: int):
    """Best-effort — a failed cache write should never fail the request
    that computed the value."""
    redis = _get_redis()
    if redis is None:
        return
    try:
        redis.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        logger.warning("Cache write failed for key=%s.", key, exc_info=True)
