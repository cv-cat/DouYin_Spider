"""任务路由 + WebSocket 进度流。"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from webapp.backend import deps

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_tasks():
    return deps.get_task_manager().list()


@router.get("/{task_id}")
async def get_task(task_id: str):
    t = deps.get_task_manager().get(task_id)
    if t is None:
        from fastapi import HTTPException
        raise HTTPException(404, "任务不存在")
    return t


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    deps.get_task_manager().delete(task_id)
    return {"ok": True}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    ok = deps.get_task_manager().cancel(task_id)
    return {"ok": ok}


@router.websocket("/ws")
async def tasks_ws(ws: WebSocket):
    await ws.accept()
    bus = deps.get_event_bus()
    q = bus.subscribe("tasks")
    try:
        # 连接时先推一份当前快照
        await ws.send_json({"type": "task.snapshot", "data": deps.get_task_manager().list()})
        while True:
            evt = await q.get()
            await ws.send_json(evt)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe("tasks", q)
