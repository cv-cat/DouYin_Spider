"""直播路由 + WebSocket 事件流。"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from webapp.backend import deps
from webapp.backend.routers._common import active_auth

router = APIRouter(prefix="/live", tags=["live"])


@router.post("/start")
async def start(body: dict):
    return deps.get_live_service().start(body["room_id"], active_auth())


@router.post("/stop")
async def stop(body: dict):
    return deps.get_live_service().stop(body["room_id"])


@router.get("/status")
async def status():
    return {"rooms": deps.get_live_service().status()}


@router.post("/digg")
async def digg(body: dict):
    return await deps.get_live_service().digg(active_auth(), body["room_id"], body.get("count", "1"))


@router.post("/send")
async def send(body: dict):
    return await deps.get_live_service().send(active_auth(), body["room_id"], body["content"])


@router.websocket("/ws/{room_id}")
async def live_ws(ws: WebSocket, room_id: str):
    await ws.accept()
    bus = deps.get_event_bus()
    channel = f"live:{room_id}"
    q = bus.subscribe(channel)
    try:
        await ws.send_json({"type": "live.status", "data": {"state": "subscribed", "room_id": room_id}})
        while True:
            evt = await q.get()
            await ws.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(channel, q)
