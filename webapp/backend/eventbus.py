"""进程内事件总线:把后台 SDK 线程的事件转发给 FastAPI WebSocket 订阅者。"""
import asyncio
from typing import Any


class EventBus:
    def __init__(self):
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subs.setdefault(channel, set()).add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue):
        subs = self._subs.get(channel)
        if subs and q in subs:
            subs.discard(q)
            if not subs:
                self._subs.pop(channel, None)

    def publish(self, channel: str, msg: Any):
        """从任意线程发布事件;丢弃满队列上的慢消费者。"""
        subs = self._subs.get(channel)
        if not subs:
            return
        for q in list(subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # 慢消费者:丢弃,避免阻塞后台线程


# 全局单例
event_bus = EventBus()
