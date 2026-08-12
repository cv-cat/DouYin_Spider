"""私信路由 + WebSocket 入站消息流。"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from webapp.backend import deps
from webapp.backend.routers._common import active_auth

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/conversation")
async def create_conversation(body: dict):
    auth = active_auth()
    ms = deps.get_message_service()
    uid = await ms.resolve_uid(auth, body.get("user_url", ""), body.get("to_user_id"))
    cid, short_id, ticket = await ms.create_conversation(auth, uid)
    return {"conversation_id": cid, "conversation_short_id": short_id,
            "ticket": ticket, "to_user_id": uid}


@router.post("/send")
async def send(body: dict):
    """一键发送:解析 uid → 建会话 → 发送。也可复用已有会话。"""
    auth = active_auth()
    ms = deps.get_message_service()
    if body.get("conversation_id") and body.get("conversation_short_id") is not None and body.get("ticket"):
        ok = await ms.send_msg(auth, body["conversation_id"], int(body["conversation_short_id"]),
                               body["ticket"], body["content"])
        return {"success": ok, "conversation_id": body["conversation_id"],
                "conversation_short_id": body["conversation_short_id"], "ticket": body["ticket"]}
    return await ms.send_to_user(auth, body["content"],
                                 body.get("to_user_id"), body.get("user_url"))


@router.post("/recv/start")
async def recv_start():
    return deps.get_message_service().start_recv(active_auth())


@router.post("/recv/stop")
async def recv_stop():
    return deps.get_message_service().stop_recv()


@router.get("/recv/status")
async def recv_status():
    return {"running": deps.get_message_service().status()}


@router.websocket("/ws")
async def messages_ws(ws: WebSocket):
    await ws.accept()
    bus = deps.get_event_bus()
    q = bus.subscribe("messages")
    try:
        await ws.send_json({"type": "msg.status", "data": {"state": "subscribed"}})
        while True:
            evt = await q.get()
            await ws.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe("messages", q)
