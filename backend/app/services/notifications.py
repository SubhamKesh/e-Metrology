"""
WebSocket notification fan-out, scoped per recipient.

Two problems this module solves, both about *who* and *where*:

1. Cross-instance delivery. Each server instance only holds the WebSocket
   connections it personally accepted -- a socket can't be handed to
   another process. So with more than one instance, a plain in-process
   broadcast only reaches clients connected to whichever instance handled
   the triggering request. Fix: every instance subscribes to one Redis
   pub/sub channel (see ws_pubsub.py). broadcast() publishes once; every
   instance, including the publisher, receives it and forwards it to its
   own local clients via local_broadcast(). Without REDIS_URL,
   broadcast() calls local_broadcast() directly -- correct for a single
   instance / local dev, same opt-in fix as middleware/ddos_store.py.

2. Who is allowed to see a message. Every connection is registered with
   the identity it authenticated as (user id, role, jurisdiction), and
   every message carries an *audience* describing who it concerns.
   Delivery is decided per connection by _should_deliver(), and it fails
   closed: a message with no audience reaches admins only, and an officer
   with no jurisdiction on file receives nothing. This mirrors the HTTP
   side (owners see their own records, officers see their jurisdiction,
   admins see everything) so the real-time channel can't leak what the
   API would have refused to return.

   Audience keys (all optional, all strings):
     owner_id       -- the owner the record belongs to
     officer_id     -- an officer specifically involved (e.g. assigned)
     state_code     -- jurisdiction the record falls under
     district_code  -- ditto, district level

A wrinkle for callers: broadcast() is a coroutine, but routers like
submit_application are plain `def` routes, which FastAPI runs in a
threadpool -- there is no running event loop in that thread.
`asyncio.create_task(...)` from there raises "no running event loop",
which a broad `except Exception` swallows, so the notification is silently
dropped. Plain `def` routes must call broadcast_threadsafe(), which
schedules onto the real loop via asyncio.run_coroutine_threadsafe.
"""
import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import WebSocket

from app.config.settings import REDIS_URL

logger = logging.getLogger("maapsetu")

NOTIFICATIONS_CHANNEL = "maapsetu:ws:notifications"

# This process's own connected clients only, mapped to the identity each
# one authenticated as. Never shared across instances directly (that's
# what the Redis channel is for).
#
# The identity is a snapshot taken at connect time: if an admin changes
# someone's jurisdiction or role later, their open connection keeps the old
# scope until it reconnects.
_clients: Dict[WebSocket, dict] = {}

# Lazily created shared publisher connection. Deliberately separate from
# the subscriber's own connection in ws_pubsub.py -- a connection actively
# subscribed to a channel is dedicated to receiving pushed messages, so
# publishing happens over its own connection instead.
_redis_publisher = None

# Set once at startup (main.py's on_startup, which genuinely runs on the
# event loop) so threadpool-worker callers have something to schedule
# work onto. None until then -- see broadcast_threadsafe()'s handling.
_event_loop: Optional[asyncio.AbstractEventLoop] = None


def _json_default(obj):
    # datetimes are the practical case (e.g. ApplicationOut.created_at, and
    # each history entry's "at", via to_application_out(doc).dict()) --
    # plain json.dumps() can't serialize a raw datetime at all. isoformat()
    # for datetimes, str() as a catch-all (e.g. a stray ObjectId), rather
    # than crashing and silently dropping the notification.
    from datetime import datetime

    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _safe_json_dumps(payload: dict) -> str:
    return json.dumps(payload, default=_json_default)


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


def _get_publisher():
    global _redis_publisher
    if _redis_publisher is None and REDIS_URL:
        from redis.asyncio import Redis

        _redis_publisher = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_publisher


# A second, plain *synchronous* publisher connection -- for processes that
# aren't the FastAPI app itself and have no local WebSocket clients or
# asyncio event loop to speak of. Specifically: the RQ background worker
# (see services/jobs.py, run_worker.py). publish_notification_sync() below
# publishes directly to the same Redis channel every FastAPI instance's
# subscriber (ws_pubsub.py) is already listening on, so a job finishing in
# a completely separate process can still reach connected clients through
# the exact same fan-out path as everything else here -- no second
# notification mechanism to build or keep in sync with this one.
_redis_sync_publisher = None


def _get_sync_publisher():
    global _redis_sync_publisher
    if _redis_sync_publisher is None and REDIS_URL:
        import redis as redis_sync

        _redis_sync_publisher = redis_sync.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_sync_publisher


def publish_notification_sync(payload: dict, audience: Optional[dict] = None) -> None:
    """For a process with no local `_clients` to fall back to (unlike
    broadcast()) -- silently no-ops without REDIS_URL, since there's
    nothing else this could do in that case."""
    redis = _get_sync_publisher()
    if redis is None:
        return
    try:
        envelope = {"audience": audience, "payload": payload}
        redis.publish(NOTIFICATIONS_CHANNEL, _safe_json_dumps(envelope))
    except Exception:
        logger.warning("Sync Redis publish (from a worker process) for a WS notification failed.", exc_info=True)


async def register(ws: WebSocket, identity: dict):
    """identity: {"user_id", "role", "state_code", "district_code"} -- the
    last two are None for owners/admins and for state-level officers'
    district."""
    _clients[ws] = identity


async def unregister(ws: WebSocket):
    _clients.pop(ws, None)


def _should_deliver(identity: dict, audience: Optional[dict]) -> bool:
    """Whether a connection authenticated as `identity` may receive a
    message addressed to `audience`. Fails closed."""
    role = identity.get("role")
    if role == "admin":
        return True  # national scope, same as the HTTP side
    if not audience:
        return False  # no stated audience -> admins only

    user_id = identity.get("user_id")
    if role == "owner":
        return user_id is not None and user_id == audience.get("owner_id")

    if role in ("lmo", "gatc"):
        if user_id is not None and user_id == audience.get("officer_id"):
            return True
        state_code = identity.get("state_code")
        if state_code is None or state_code != audience.get("state_code"):
            return False  # includes officers with no jurisdiction on file
        district_code = identity.get("district_code")
        # district_code None on the officer = state-level scope
        return district_code is None or district_code == audience.get("district_code")

    return False


async def local_broadcast(payload: dict, audience: Optional[dict] = None):
    """Sends to this process's own connected clients, filtered to those
    the audience allows. Called directly by broadcast() when there's no
    Redis, and by the pub/sub subscriber (ws_pubsub.py) whenever a message
    arrives on the shared channel, from any instance including this one."""
    if not _clients:
        return
    data = _safe_json_dumps(payload)
    coros = []
    for ws, identity in list(_clients.items()):
        if not _should_deliver(identity, audience):
            continue
        try:
            coros.append(ws.send_text(data))
        except Exception:
            # ignore send errors; cleanup happens elsewhere
            pass
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)


async def broadcast(payload: dict, audience: Optional[dict] = None):
    """Fan a notification out across every instance, delivered only to the
    connections `audience` allows. Call directly only from a coroutine
    already on the event loop; from a plain `def` (threadpool) route use
    broadcast_threadsafe() -- see the module docstring."""
    publisher = _get_publisher()
    if publisher is not None:
        try:
            envelope = {"audience": audience, "payload": payload}
            await publisher.publish(NOTIFICATIONS_CHANNEL, _safe_json_dumps(envelope))
            return
        except Exception:
            logger.warning(
                "Redis publish for a WS notification failed; falling back "
                "to local-only delivery for this message.",
                exc_info=True,
            )
    await local_broadcast(payload, audience)


def broadcast_threadsafe(payload: dict, audience: Optional[dict] = None) -> None:
    """What a plain `def` (threadpool) route should call -- schedules
    broadcast() onto the real event loop from whatever thread this is
    running on. Best-effort and non-blocking: doesn't wait for delivery,
    and a failure here should never fail the request that triggered it."""
    if _event_loop is None:
        logger.warning("broadcast_threadsafe() called before the event loop was captured at startup; dropping this notification.")
        return
    try:
        asyncio.run_coroutine_threadsafe(broadcast(payload, audience), _event_loop)
    except Exception:
        logger.warning("Failed to schedule a WS broadcast from a worker thread.", exc_info=True)
