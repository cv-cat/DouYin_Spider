"""进程内异步任务管理器:跑长任务(采集/搜索/评论),带进度与事件推送。"""
import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from webapp.backend.eventbus import event_bus


class TaskInfo:
    def __init__(self, kind: str, params: dict):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.params = params
        self.status = "pending"
        self.progress = 0.0
        self.result: Any = None
        self.error: Optional[str] = None
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.finished_at: Optional[str] = None
        self._cancel = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "progress": self.progress, "result": self.result, "error": self.error,
            "created_at": self.created_at, "finished_at": self.finished_at,
            "params": self.params,
        }


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}
        self._loop = asyncio.get_event_loop()

    def list(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    def get(self, task_id: str) -> Optional[dict]:
        t = self._tasks.get(task_id)
        return t.to_dict() if t else None

    def cancel(self, task_id: str) -> bool:
        t = self._tasks.get(task_id)
        if t and t.status in ("pending", "running"):
            t._cancel = True
            t.status = "cancelled"
            t.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._emit(t)
            return True
        return False

    def delete(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def submit(self, kind: str, func: Callable, *args, params: Optional[dict] = None,
               label: str = "") -> str:
        """提交一个同步阻塞函数,在线程池执行。func 签名:(progress_cb, *args) -> result。
        progress_cb(pct: float, partial: Any = None)。"""
        info = TaskInfo(kind, params or {})
        if label:
            info.params.setdefault("label", label)
        self._tasks[info.id] = info

        def progress_cb(pct: float, partial: Any = None):
            # 来自工作线程,需线程安全地回到事件循环
            self._loop.call_soon_threadsafe(self._on_progress, info.id, pct, partial)

        async def runner():
            info.status = "running"
            self._emit(info)
            try:
                result = await asyncio.to_thread(func, progress_cb, *args)
                if info._cancel:
                    return
                info.result = result
                info.progress = 1.0
                info.status = "done"
            except Exception as e:
                if info._cancel:
                    return
                info.status = "failed"
                info.error = str(e)
            info.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._emit(info)

        asyncio.create_task(runner())
        return info.id

    def _on_progress(self, task_id: str, pct: float, partial: Any):
        t = self._tasks.get(task_id)
        if not t or t._cancel:
            return
        t.progress = pct
        if partial is not None:
            t.result = partial
        t.status = "running"
        self._emit(t)

    def _emit(self, t: TaskInfo):
        evt_type = {"done": "task.done", "failed": "task.failed",
                    "cancelled": "task.cancelled"}.get(t.status, "task.progress")
        event_bus.publish("tasks", {"type": evt_type, "data": t.to_dict()})
