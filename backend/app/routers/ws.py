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
            user = users_col.find_one({"_id": __import__("bson").ObjectId(user_id)})
            if not user:
                await ws.close(code=1008)
                return
        else:
            # no token provided; reject
            await ws.close(code=1008)
            return
    except Exception:
        await ws.close(code=1008)
        return

    try:
        await register(ws)
        while True:
            await ws.receive_text()  # keep connection open; ignore incoming messages
    except WebSocketDisconnect:
        await unregister(ws)
    except Exception:
        await unregister(ws)
