from bson import ObjectId
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.notifications import register, unregister
from app.utils.security import decode_token
from app.config.db import users_col

router = APIRouter()


@router.websocket("/ws/notifications")
async def notifications_ws(ws: WebSocket):
    # Accept and perform a simple token check via query param ?token=...
    await ws.accept()
    token = ws.query_params.get("token")
    try:
        if token:
            user_id = decode_token(token)
            # confirm user exists
            user = users_col.find_one({"_id": ObjectId(user_id)})
            # An account that's been rejected/suspended shouldn't keep
            # receiving notifications just because it still holds a token
            # that hasn't expired yet.
            if not user or user.get("status") != "active":
                await ws.close(code=1008)
                return
        else:
            # no token provided; reject
            await ws.close(code=1008)
            return
    except Exception:
        await ws.close(code=1008)
        return

    # What this connection is allowed to receive is decided per message
    # in services/notifications.py (_should_deliver), from this identity.
    jurisdiction = user.get("jurisdiction") or {}
    identity = {
        "user_id": str(user["_id"]),
        "role": user.get("role"),
        "state_code": jurisdiction.get("state_code"),
        "district_code": jurisdiction.get("district_code"),
    }

    try:
        await register(ws, identity)
        while True:
            await ws.receive_text()  # keep connection open; ignore incoming messages
    except WebSocketDisconnect:
        await unregister(ws)
    except Exception:
        await unregister(ws)
