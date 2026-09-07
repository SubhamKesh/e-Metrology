import asyncio
import json
from typing import Set

from fastapi import WebSocket

_clients: Set[WebSocket] = set()


async def register(ws: WebSocket):
    _clients.add(ws)


async def unregister(ws: WebSocket):
    _clients.discard(ws)


async def broadcast(payload: dict):
    if not _clients:
        return
    data = json.dumps(payload)
    coros = []
    for ws in list(_clients):
        try:
            coros.append(ws.send_text(data))
        except Exception:
            # ignore send errors; cleanup happens elsewhere
            pass
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)
