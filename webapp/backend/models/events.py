"""WebSocket 事件信封。"""
from typing import Any, Optional

from pydantic import BaseModel


class Event(BaseModel):
    type: str
    data: dict[str, Any] = {}
    ts: Optional[int] = None


# 直播事件类型:live.gift / live.chat / live.member / live.like / live.social / live.room_stats / live.status
# 私信事件类型:msg.text / msg.emoji / msg.voice / msg.image / msg.video / msg.read / msg.raw
# 任务事件类型:task.progress / task.done / task.failed
