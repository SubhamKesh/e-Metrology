"""
Cross-instance fan-out for WebSocket notifications (see notifications.py
for the full picture). This is the other half: the long-running background
task that keeps every instance's local clients in sync with every other
instance's activity.

Started once per process at app startup (see main.py) -- only when
REDIS_URL is set. Runs until cancelled at shutdown. If the Redis
connection drops mid-run, it retries with backoff rather than dying --
a flaky Redis shouldn't permanently kill cross-instance notifications for
the rest of this process's lifetime.
"""
import asyncio
import json
import logging

from app.config.settings import REDIS_URL
from app.services.notifications import NOTIFICATIONS_CHANNEL, local_broadcast

logger = logging.getLogger("maapsetu")


async def run_ws_subscriber():
    if not REDIS_URL:
        return

    from redis.asyncio import Redis

    backoff = 1
    while True:
        try:
            redis = Redis.from_url(REDIS_URL, decode_responses=True)
            pubsub = redis.pubsub()
            await pubsub.subscribe(NOTIFICATIONS_CHANNEL)
            logger.info("WS notification subscriber connected (channel=%s).", NOTIFICATIONS_CHANNEL)
            backoff = 1  # reset after a successful (re)connect

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                    payload = envelope["payload"]
                    audience = envelope.get("audience")
                except (TypeError, ValueError, KeyError):
                    # Malformed message from somewhere -- skip it rather
                    # than crash the whole subscriber loop over one bad
                    # message.
                    continue
                await local_broadcast(payload, audience)

        except asyncio.CancelledError:
            # Normal shutdown path (see main.py's shutdown handler) -- not
            # an error, don't log or retry.
            raise
        except Exception:
            logger.warning(
                "WS notification Redis subscriber lost connection; retrying in %ss.",
                backoff,
                exc_info=True,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
